"""Abstraction of the modem interface."""

import ipaddress
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pyatcommand import AtClient, AtErrorCode
from pyatcommand.utils import dprint

from .constants import (
    Chipset,
    ModuleManufacturer,
    ModuleModel,
    PdpType,
    RegistrationState,
    NtnOpMode,
    GnssFixType,
    UrcType,
    TauMultiplier,
    ActMultiplier,
    EdrxCycle,
    EdrxPtw,
    SignalLevel,
    SignalQuality,
)
from .ntninit import generic

__all__ = [
    'NtnLocation',
    'RegInfo',
    'SigInfo',
    'PdpContext',
    'PsmConfig',
    'EdrxConfig',
    'SocketStatus',
    'MtMessage',
    'NbntnModem',
]

_log = logging.getLogger(__name__)


@dataclass
class NtnLocation:
    """Attributes of a NTN location.
    
    Used for purposes of registration and/or Tracking Area Update.
    """
    lat_deg: Optional[float] = None
    lon_deg: Optional[float] = None
    alt_m: Optional[float] = None
    spd_mps: Optional[float] = None
    cep_rms: Optional[int] = None
    opmode: Optional[NtnOpMode] = None
    fix_type: Optional[GnssFixType] = None
    fix_timestamp: Optional[int] = None
    hdop: Optional[float] = None
    satellites: Optional[int] = None
    
    @property
    def fix_time_iso(self) -> str:
        if not self.fix_timestamp:
            return ''
        iso_time = datetime.fromtimestamp(self.fix_timestamp, tz=timezone.utc).isoformat()
        return f'{iso_time[:19]}Z'


@dataclass
class RegInfo:
    """Attributes of NTN registration state."""
    state: RegistrationState = RegistrationState.UNKNOWN
    tac: str = ''
    ci: str = ''
    cause_type: int = 0
    reject_cause: int = 0
    active_time_bitmask: str = ''
    tau_bitmask: str = ''
    
    def is_registered(self) -> bool:
        return self.state in [RegistrationState.HOME, RegistrationState.ROAMING]


@dataclass
class SigInfo:
    """Attributes of NB-NTN relevant signal level information."""
    rsrp: int = 255   # Reference Signal Received Power (dBm)
    rsrq: int = 255   # Reference Signal Received Quality (dB)
    sinr: int = 255   # Signal Interference + Noise Ratio (dB)
    rssi: int = 99   # Received signal strength indicator (dB)
    ber: float = 99.0   # Channel bit error rate %


@dataclass
class PdpContext:
    """Attributes of a NB-NTN Packet Data Protocol context/definition."""
    id: int = 1   # context ID
    pdp_type: PdpType = PdpType.IP
    apn: str = ''
    ip: 'str|None' = ''   # the IP address if type is IP and attached


@dataclass
class PsmConfig:
    """Power Saving Mode configuration attributes."""
    tau_t3412_bitmask: str = ''   # TAU timer - when the modem updates its location
    act_t3324_bitmask: str = ''   # Activity timer - how long the modem stays awake after TAU
    
    @staticmethod
    def tau_seconds(bitmask: str) -> int:
        """Convert a TAU bitmask to seconds."""
        if not bitmask:
            return 0
        tvu = (int(bitmask, 2) & 0b11100000) >> 5   # timer value unit
        bct = int(bitmask, 2) & 0b00011111   # binary coded timer value
        if TauMultiplier(tvu) == TauMultiplier.DEACTIVATED:
            return 0
        unit, multiplier = TauMultiplier(tvu).name.split('_')
        if unit == 'H':
            return bct * int(multiplier) * 3600
        if unit == 'M':
            return bct * int(multiplier) * 60
        return bct * int(multiplier)
    
    @staticmethod
    def seconds_to_tau(seconds: int) -> str:
        """Convert an integer value to a TAU bitmask."""
        if not isinstance(seconds, int) or seconds == 0:
            return f'{(TauMultiplier.DEACTIVATED << 5):08b}'
        MAX_TAU = 31 * 320 * 3600
        if seconds > MAX_TAU:
            seconds = MAX_TAU
        multipliers = [2, 30, 60, 3600, 10*3600]
        bct = None
        tvu = None
        for i, m in enumerate(multipliers):
            if seconds <= 31 * m:
                bct = int(seconds / m)
                tvu = TauMultiplier(i).value << 5
                break
        if tvu is None:
            bct = int(seconds / (320 * 3600))
            tvu = TauMultiplier.H_320.value << 5
        return f'{(tvu & bct):08b}'
    
    @staticmethod
    def act_seconds(bitmask: str) -> int:
        """Convert the bitmask to Active PSM seconds."""
        if not bitmask:
            return 0
        tvu = (int(bitmask, 2) & 0b11100000) >> 5   # timer value unit
        bct = int(bitmask, 2) & 0b00011111   # binary coded timer value
        if ActMultiplier(tvu) == ActMultiplier.DEACTIVATED:
            return 0
        unit, multiplier = ActMultiplier(tvu).name.split('_')
        if unit == 'H':
            return bct * int(multiplier) * 3600
        if unit == 'M':
            return bct * int(multiplier) * 60
        return bct * int(multiplier)
    
    @staticmethod
    def seconds_to_act(seconds: int) -> str:
        """Convert active time seconds to the ACT bitmask."""
        if not isinstance(seconds, int) or seconds == 0:
            return f'{(ActMultiplier.DEACTIVATED << 5):08b}'
        MAX_ACT = 31 * 6 * 60
        if seconds > MAX_ACT:
            seconds = MAX_ACT
        multipliers = [2, 60]
        bct = None
        tvu = None
        for i, m in enumerate(multipliers):
            if seconds <= (31 * m):
                bct = int(seconds / m)
                tvu = ActMultiplier(i).value << 5
                break
        if tvu is None:
            bct = int(seconds / (6 * 60))
            tvu = ActMultiplier.M_6 << 5
        return f'{(tvu & bct):08b}'
    
    @property
    def tau_s(self) -> int:
        """The requested TAU interval in seconds."""
        return PsmConfig.tau_seconds(self.tau_t3412_bitmask)
    
    @property
    def act_s(self) -> int:
        """The requested Activity duration in seconds."""
        return PsmConfig.act_seconds(self.act_t3324_bitmask)


@dataclass
class EdrxConfig:
    """Extended Discontiguous Receive mode configuration attributes."""
    cycle_bitmask: str = ''
    ptw_bitmask: str = ''

    @staticmethod
    def edrx_cycle_seconds(bitmask: str) -> int:
        """Calculate the eDRX cycle time from the bitmask."""
        try:
            tvu = int(bitmask, 2)
            if tvu > 15:
                raise ValueError('Invalid bitmask')
            return int(EdrxCycle(tvu).name.split('_')[1])
        except ValueError:
            return 0
    
    @staticmethod
    def seconds_to_edrx_cycle(seconds: 'int|float') -> str:
        """Convert nearest seconds to eDRX cycle bitmask"""
        MAX_EDRX_CYCLE = 10485
        if seconds > MAX_EDRX_CYCLE:
            seconds = MAX_EDRX_CYCLE
        edrx_values = [5, 10, 20, 40, 60, 80, 160, 325, 655, 1310, 2620, 5240]
        for i, v in enumerate(edrx_values):
            if seconds <= v:
                return f'{EdrxCycle(i).value:04b}'
        return f'{EdrxCycle.S_10485.value:04b}'
    
    @staticmethod
    def edrx_ptw_seconds(bitmask: str) -> int:
        """Calculate the eDRX cycle time from the bitmask."""
        try:
            tvu = int(bitmask, 2)
            if tvu > 15:
                raise ValueError('Invalid bitmask')
            return int(EdrxPtw(tvu).name.split('_')[1])
        except ValueError:
            return 0
    
    @staticmethod
    def seconds_to_edrx_ptw(seconds: 'int|float') -> str:
        """Convert seconds to Paging Time Window bitmask"""
        MAX_PTW = 40
        if seconds > MAX_PTW:
            seconds = MAX_PTW
        ptw_values = [2, 5, 7, 10, 12, 15, 17, 20, 23, 25, 28, 30, 33, 35, 38]
        for i, v in enumerate(ptw_values):
            if seconds <= v:
                return f'{EdrxPtw(i).value:04b}'
        return f'{EdrxPtw.S_40.value:04b}'
    
    @property
    def cycle_s(self) -> float:
        """The requested eDRX cycle time in seconds."""
        return EdrxConfig.edrx_cycle_seconds(self.cycle_bitmask)
    
    @property
    def ptw_s(self) -> float:
        """The requested eDRX Paging Time Window in seconds."""
        return EdrxConfig.edrx_ptw_seconds(self.ptw_bitmask)


@dataclass
class SocketStatus:
    """Metadata for a UDP socket including state and IP address"""
    active: bool = False
    ip_address: str = ''


@dataclass
class MtMessage:
    """Metadata for Mobile-Terminated message including payload and source"""
    payload: 'bytes|None' = None
    src_ip: Optional[str] = None
    src_port: Optional[int] = None


class NbntnModem:
    """Abstraction for a NB-NTN modem."""

    _manufacturer: ModuleManufacturer = ModuleManufacturer.UNKNOWN
    _model: ModuleModel = ModuleModel.UNKNOWN
    _chipset: Chipset = Chipset.UNKNOWN
    _ignss: bool = False
    _ntn_only: bool = False

    def __init__(self, **kwargs) -> None:
        """Instantiate a modem interface.
        
        Args:
            **client (AtClient): The AT client serial connection
            **pdp_type (PdpType): Optional PDP context type, default `NON_IP`
            **apn (str): Optional APN
            **udp_server (str): Optional IP or URL of the server if using UDP
            **udp_port (int): Optional destination port of the server if using UDP
        """
        self._version: str = ''
        self._serial_port = kwargs.get('port', os.getenv('SERIAL_PORT',
                                                         '/dev/ttyUSB0'))
        self._baudrate = kwargs.get('baudrate', int(os.getenv('SERIAL_BAUDRATE',
                                                              115200)))
        self._serial: AtClient = kwargs.get('client', AtClient())
        if not isinstance(self._serial, AtClient):
            raise ValueError('Invalid AtClient')
        self._pdp_type: PdpType = kwargs.get('pdp_type', PdpType.NON_IP)
        if not isinstance(self._pdp_type, PdpType):
            raise ValueError('Invalid PdpType')
        self._apn: str = ''
        self.apn = kwargs.get('apn', '')
        self._udp_server: str = ''
        self.udp_server = kwargs.get('udp_server', '')
        self._udp_server_port: int = 0
        self.udp_server_port = kwargs.get('udp_port', 0)
    
    def connect(self, **kwargs) -> None:
        """Connect to the modem UART/serial"""
        if 'port' not in kwargs:
            kwargs['port'] = self._serial_port
        if 'baudrate' not in kwargs:
            kwargs['baudrate'] = self._baudrate
        self._serial.connect(**kwargs)
        self._baudrate = self._serial.baudrate

    def is_connected(self) -> bool:
        """Check if the modem UART/serial is connected"""
        return self._serial.is_connected()
    
    def disconnect(self) -> None:
        """Disconnect from the modem UART/serial"""
        self._serial.disconnect()
        self._version = ''

    def send_command(self, at_command: str, timeout: float = 1) -> AtErrorCode:
        """Send an arbitrary AT command and get the result code."""
        return self._serial.send_at_command(at_command, timeout)
    
    def get_response(self, prefix: str = '') -> 'str|None':
        """Get the response from the prior `send_command` or `check_urc`."""
        return self._serial.get_response(prefix)
    
    def check_urc(self, **kwargs) -> bool:
        """Check for an Unsolicited Result Code.
        
        Args:
            **read_until (str): Optional terminating string (default `<cr><lf>`)
            **timeout (float): Maximum seconds to wait for completion if data
            is found (default `AT_URC_TIMEOUT` 0.3 seconds)
            **prefix (str): Optional expected prefix for a URC (default `+`)
            **prefixes (list[str]): Optional multiple prefix options
            **wait: Optional additional seconds to wait for the prefix

        """
        return self._serial.check_urc(**kwargs)
    
    def get_sleep_mode(self):
        """Get the modem hardware sleep settings."""
        raise NotImplementedError('Requires module-specfic subclass')

    def set_sleep_mode(self):
        """Set the modem hardware sleep settings."""
        raise NotImplementedError('Requires module-specfic subclass')

    def get_error_mode(self) -> int:
        """Get the CMEE error mode configuration"""
        if self.send_command('AT+CMEE?') == AtErrorCode.OK:
            return int(self.get_response())
        return 0
    
    def set_error_mode(self, mode: int) -> bool:
        """Set the CMEE error mode configuration"""
        if mode not in [0, 1, 2]:
            raise ValueError('Invalid CMEE setting')
        return self.send_command(f'AT+CMEE={mode}') == AtErrorCode.OK

    @property
    def manufacturer(self) -> str:
        return self._manufacturer.name
    
    @classmethod
    def model_name(self) -> str:
        return self._model.name
    
    @property
    def model(self) -> str:
        return self._model.name
    
    @property
    def chipset(self) -> str:
        return self._chipset.name
    
    @property
    def module_version(self) -> str:
        if not self._version:
            if self.send_command('AT+CGMR') == AtErrorCode.OK:
                rev = self.get_response()
                if ':' in rev:
                    rev = rev.split(':')[1].strip()
                self._version = rev
        return self._version
    
    @property
    def has_ignss(self) -> bool:
        return self._ignss
    
    @property
    def ntn_only(self) -> bool:
        return self._ntn_only
    
    @property
    def pdp_type(self) -> PdpType:
        return self._pdp_type
    
    @pdp_type.setter
    def pdp_type(self, pdp_type: PdpType):
        if not isinstance(pdp_type, PdpType):
            raise ValueError('Invalid PDP Type')
        self._pdp_type = pdp_type

    @property
    def ip_address(self) -> str:
        ip_address = ''
        if self.send_command('AT+CGDCONT?') == AtErrorCode.OK:
            params = self.get_response('+CGDCONT:').split(',')
            for i, param in enumerate(params):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 3:
                    ip_address = param
        return ip_address

    @property
    def apn(self) -> str:
        return self._apn
    
    @apn.setter
    def apn(self, name: str):
        if not isinstance(name, str):
            raise ValueError('Invalid APN')
        self._apn = name
    
    @property
    def udp_server(self) -> str:
        return self._udp_server
    
    @udp_server.setter
    def udp_server(self, server: str):
        if (not server or
            (not is_valid_ip(server) and not is_valid_hostname(server))):
            _log.error('Invalid server IP or DNS')
            return
        self._udp_server = server
    
    @property
    def udp_server_port(self) -> int:
        return self._udp_server_port
    
    @udp_server_port.setter
    def udp_server_port(self, port: int):
        if not isinstance(port, int) or port not in range(0, 65536):
            raise ValueError('Invalid UDP port')
        self._udp_server_port = port
    
    def is_asleep(self) -> bool:
        """Check if the modem is in deep sleep state."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def get_imsi(self) -> 'str':
        """Get the IMSI of the SIM installed with the modem."""
        if self.send_command('AT+CIMI', 5) == AtErrorCode.OK:
            return self.get_response()
        return ''
    
    def initialize_ntn(self, **kwargs) -> bool:
        """Execute the modem-specific initialization to communicate on NTN."""
        ntn_init: 'list[dict]' = kwargs.get('ntn_init', [])
        if not ntn_init:
            _log.warning('Using generic modem initialization sequence')
            ntn_init = generic
        for seq in ntn_init:
            if 'delay' in seq and isinstance(seq['delay'], (int, float)):
                time.sleep(seq['delay'])
            if 'cmd' not in seq:
                _log.info('Skipping: %s', seq)
                continue
            at_cmd: str = seq.get('cmd')
            timeout = seq.get('timeout', 1)
            attempt = 1
            if '<pdn_type>' in at_cmd:
                pdn_type = self._pdp_type.name
                if 'non' in pdn_type.lower():
                    pdn_type = 'NON-IP'
                at_cmd = at_cmd.replace('<pdn_type>', pdn_type)
            if '<apn>' in at_cmd:
                if self._apn:
                    at_cmd = at_cmd.replace('<apn>', self._apn)
                else:
                    at_cmd = at_cmd.replace(',"<apn>"', '')
            if (self.send_command(at_cmd, timeout=timeout) != seq['res']):
                _log.error('Failed to %s', seq['why'])
                if 'retry' in seq:
                    retry: dict = seq.get('retry')
                    if retry.get('count') > 0:
                        if attempt > retry['count']:
                            return False
                        delay = retry.get('delay', 1)
                        _log.warning('Retrying in %0.1f seconds', delay)
                        time.sleep(delay)
                    attempt += 1
                else:
                    return False
            if 'urc' in seq:
                urc_kwargs = { 'prefixes': ['+', '%'] }
                if 'urctimeout' in seq:
                    urc_kwargs['timeout'] = seq['urctimeout']
                urc = self.await_urc(seq['urc'], **urc_kwargs)
                if urc != seq['urc']:
                    _log.error('Received %s but expected %s', urc, seq['urc'])
                    return False
        return True
    
    def await_urc(self, urc: str = '', **kwargs) -> str:
        """Wait for an unsolicited result code or timeout."""
        _log.info('Waiting for unsolicited %s', urc)
        timeout = float(kwargs.get('timeout', 0))
        prefixes = kwargs.get('prefixes', ['+', '%'])
        wait_start = time.time()
        while timeout == 0 or time.time() - wait_start < timeout:
            if self.check_urc(prefixes=prefixes):
                candidate = self.get_response()
                if urc and candidate.startswith(urc):
                    _log.debug('%s received after %0.1f seconds',
                               candidate, time.time() - wait_start)
                    return candidate
            else:
                time.sleep(1)
        return ''
    
    def get_info(self) -> str:
        """Get the detailed response of the AT information command."""
        if self.send_command('ATI', timeout=3) == AtErrorCode.OK:
            return self.get_response()
        return ''
    
    def get_imei(self) -> str:
        """Get the modem's IMEI number.
        
        International Mobile Equipment Identity
        """
        if self.send_command('AT+CGSN=1') == AtErrorCode.OK:
            return self.get_response('+CGSN:').replace('"', '')
        return ''
    
    def use_ignss(self, enable: bool = True, **kwargs) -> bool:
        """Use the internal GNSS for NTN network registration."""
        raise NotImplementedError('Requires module-specfic subclass')

    def get_location(self) -> NtnLocation:
        """Get the location currently in use by the modem."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def set_location(self, loc: NtnLocation, **kwargs) -> bool:
        """Set the modem location to use for registration/TAU."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def get_reginfo(self, urc: str = '') -> RegInfo:
        """Get the parameters of the registration state of the modem.
        
        Args:
            urc (str): Optional URC will be queried if not provided

        """
        info = RegInfo()
        queried = False
        if not urc:
            queried = True
            if self.send_command('AT+CEREG?') == AtErrorCode.OK:
                urc = self.get_response()
        if urc:
            cereg_parts = urc.replace('+CEREG:', '').strip().split(',')
            if (queried):
                config = int(cereg_parts.pop(0))
                _log.debug('Registration reporting mode: %d', config)
            for i, param in enumerate(cereg_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 0:
                    info.state = RegistrationState(int(param))
                    _log.debug('Registered: %s', info.state.name)
                elif i == 1 and param:
                    info.tac = param
                elif i == 2 and param:
                    info.ci = param
                # 3: Access technology of registered network
                elif i == 4 and param:
                    info.cause_type = int(param)
                elif i == 5 and param:
                    info.reject_cause = int(param)
                elif i == 6 and param:
                    info.active_time_bitmask = param
                elif i == 7 and param:
                    info.tau_bitmask = param
        return info
    
    def get_regconfig(self) -> int:
        """Get the registration reporting configuration."""
        if self.send_command('AT+CEREG?') == AtErrorCode.OK:
            config = self.get_response('+CEREG:').split(',')[0]
            return int(config)
        return -1
    
    def set_regconfig(self, config: int) -> bool:
        """Set the registration verbosity."""
        if config not in range(0, 6):
            raise ValueError('Invalid CEREG config value')
        return self.send_command(f'AT+CEREG={config}') == AtErrorCode.OK
    
    def get_siginfo(self) -> SigInfo:
        """Get the signal information from the modem."""
        info = SigInfo(255, 255, 255, 255)
        if self.send_command('AT+CESQ') == AtErrorCode.OK:
            sig_parts = self.get_response('+CESQ:').split(',')
            for i, param in enumerate(sig_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 0:   # <rxlev> offset -110 dBm
                    if param != '99':
                        info.rssi = int(float(param) - 110)
                if i == 1:   # <ber> RxQual values 3GPP 45.008
                    if int(param) <= 7:
                        rx_qual_map = {
                            0: 0.14,
                            1: 0.28,
                            2: 0.57,
                            3: 1.13,
                            4: 2.26,
                            5: 4.53,
                            6: 9.05,
                            7: 18.1,
                        }
                        info.ber = rx_qual_map[int(param)]
                # 2: <rscp> offset -120 dBm 3GPP 25.133/25.123
                # 3: <ecno> offset -24 dBm increment 0.5 3GPP 25.133
                if i == 4:   # <rsrq> offset -19.5 dB increment 0.5 3GPP 36.133
                    if param != '255':
                        info.rsrq = int(float(param) * 0.5 - 19.5)
                if i == 5:   # <rsrp> offset -140 dBm 3GPP 36.133
                    if param != '255':
                        info.rsrp = int(float(param) - 140)
        return info
    
    def get_contexts(self) -> 'list[PdpContext]':
        """Get the list of configured PDP contexts in the modem."""
        contexts: 'list[PdpContext]' = []
        if self.send_command('AT+CGDCONT?') == AtErrorCode.OK:
            context_strs = self.get_response('+CGDCONT:').split('\n')
            for s in context_strs:
                c = PdpContext()
                for i, param in enumerate(s.split(',')):
                    param = param.replace('"', '')
                    if not param:
                        continue
                    if i == 0:
                        c.id = int(param)
                    elif i == 1:
                        c.pdp_type = PdpType[param.upper().replace('-', '_')]
                    elif i == 2:
                        c.apn = param
                    elif i == 3:
                        c.ip = param
                contexts.append(c)
        return contexts
    
    def set_context(self, config: PdpContext) -> bool:
        """Configure a specific PDP context in the modem."""
        for c in self.get_contexts():
            if (c.id == config.id):
                if (c.pdp_type == config.pdp_type and
                    c.apn == config.apn):
                    return True
        if self.send_command('AT+CFUN=0', timeout=30) != AtErrorCode.OK:
            _log.error('Unable to disable radio for config')
            return False
        # TODO: await AT responsiveness
        cmd = f'AT+CGDCONT={config.id}'
        pdp_type = config.pdp_type.name.replace('_', '-')
        cmd += f',"{pdp_type}"'
        cmd += f',"{config.apn}"'
        if config.ip:
            cmd += f',{config.ip}'
        #TODO: other optional configurations
        if self.send_command(cmd) != AtErrorCode.OK:
            _log.error('Error configuring PDN context')
            return False
        return self.send_command('AT+CFUN=1', timeout=30) == AtErrorCode.OK
    
    def get_psm_config(self) -> PsmConfig:
        """Get the Power Save Mode settings."""
        config = PsmConfig()
        if self.send_command('AT+CPSMS?') == AtErrorCode.OK:
            psm_parts = self.get_response('+CPSMS:').split(',')
            for i, param in enumerate(psm_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 3:
                    config.tau_t3412_bitmask = param
                elif i == 4:
                    config.act_t3324_bitmask = param
        return config
    
    def set_psm_config(self, psm: 'PsmConfig|None' = None) -> bool:
        """Configure requested Power Saving Mode settings"""
        if psm and not isinstance(psm, PsmConfig):
            raise ValueError('Invalid PSM configuration')
        mode = 0 if psm is None else 1
        cmd = f'AT+CPSMS={mode}'
        if mode > 0:
            cmd += f',{psm.tau_t3412_bitmask},{psm.act_t3324_bitmask}'
        return self.send_command(cmd) == AtErrorCode.OK

    def get_edrx_config(self) -> EdrxConfig:
        """Get the eDRX mode settings."""
        config = EdrxConfig()
        if self.send_command('AT+CEDRXS?') == AtErrorCode.OK:
            edrx_parts = self.get_response('+CEDRXS:').split(',')
            for i, param in enumerate(edrx_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 1:
                    config.cycle_bitmask = param
                # TODO: additional?
        return config
    
    def set_edrx_config(self, edrx: 'EdrxConfig|None' = None) -> bool:
        """Configure requested Power Saving Mode settings"""
        if edrx and not isinstance(edrx, EdrxConfig):
            raise ValueError('Invalid eDRX configuration')
        mode = 0 if edrx is None else 2
        cmd = f'AT+CEDRXS={mode}'
        if mode > 0:
            cmd += f',5,{edrx.cycle_bitmask}'
        return self.send_command(cmd) == AtErrorCode.OK

    def get_edrx_dynamic(self) -> EdrxConfig:
        """Get the eDRX parameters granted by the network."""
        dynamic = EdrxConfig()
        if self.send_command('AT+CEDRXRDP') == AtErrorCode.OK:
            edrx_parts = self.get_response('+CEDRXRDP:').split(',')
            for i, param in enumerate(edrx_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 2:
                    dynamic.cycle_bitmask = param
                elif i == 3:
                    dynamic.ptw_bitmask = param
        return dynamic
    
    def use_lband(self) -> bool:
        """Restrict network scans to L-band 255."""
        raise NotImplementedError('Requires module-specific subclass')
        
    def get_band(self) -> int:
        """Get the current LTE band in use."""
        _log.warning('No module-specific subclass - returning -1')
        return -1

    def get_frequency(self) -> int:
        """Get the current frequency in use if camping on a cell."""
        _log.warning('No module-specific subclass - returning -1')
        return -1
    
    def get_urc_type(self, urc: str) -> UrcType:
        """Get the URC type to determine a handling function/parameters."""
        if not isinstance(urc, str):
            raise ValueError('Invalid URC - must be string type')
        if urc.startswith('+CEREG:'):
            return UrcType.REGISTRATION
        if urc.startswith('+CRTDCP:'):
            return UrcType.NIDD_MT_RCVD
        return UrcType.UNKNOWN

    def get_last_error(self, **kwargs) -> int:
        """Get the error code of the prior errored command.
        
        Args:
            failed_op (str): The type of operation that failed.
        
        Returns:
            An error code specific to the manufacturer/module. -1 is unknown.
            
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    def enable_nidd_urc(self, enable: bool = True, **kwargs) -> bool:
        """Enable unsolicited reporting of received Non-IP data.
        
        Downlink/MT message data received via control plane.
        """
        return self.send_command(f'AT+CRTDCP={int(enable)}') == AtErrorCode.OK

    def send_message_nidd(self, message: bytes, cid: int = 1, **kwargs) -> bool:
        """Send a message using Non-IP transport."""
        _log.warning('Sending NIDD message without confirmation')
        cmd = f'AT+CSODCP={cid},{len(message)},"{message.hex()}"'
        return self.send_command(cmd) == AtErrorCode.OK
    
    def receive_message_nidd(self, urc: str, **kwargs) -> 'bytes|None':
        """Parses a NIDD URC string to derive the MT/downlink bytes sent.
        
        Args:
            urc (str): The 3GPP standard +CRTDCP unsolicited output
        """
        received = None
        if isinstance(urc, str) and urc.startswith('+CRTDCP'):
            urc = urc.replace('+CRTDCP:', '').strip()
            params = urc.split(',')
            for i, param in enumerate(params):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 2:
                    received = bytes.fromhex(param)
        else:
            _log.error('Invalid URC: %s', urc)
        return received
    
    def ping_icmp(self, **kwargs) -> int:
        """Send a ICMP ping to a target address.
        
        Args:
            **server (str): The host to ping (default 8.8.8.8)
            **timeout (int): The timeout in seconds (default 30)
            **size (int): The size of ping in bytes (default 32)
            **count (int): The number of pings to attempt (default 1)
            **cid (int): Context ID (default 1)
        
        Returns:
            The average ping latency in milliseconds or -1 if lost
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    def enable_udp_urc(self) -> bool:
        """Enables URC supporting UDP operation."""
        # raise NotImplementedError('Must implement in subclass')
        return False
    
    def udp_socket_open(self, **kwargs) -> bool:
        """Open a UDP socket.
        
        Args:
            **server (str): The server IP or URL
            **port (int): The destination port of the server
            **cid (int): The context/session ID (default 1)
            **src_port (int): Optional source port to use when sending
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    def udp_socket_status(self, cid: int = 1) -> SocketStatus:
        """Get the status of the specified socket/context ID."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def udp_socket_close(self, cid: int = 1) -> bool:
        """Close the specified socket."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def send_message_udp(self, message: bytes, **kwargs) -> bool:
        """Send a message using UDP transport.

        Opens a socket if one does not exist and closes after sending.
        
        Args:
            message (bytes): The binary blob to be sent
            **server (str): The server IP or URL if establishing a new socket
            **port (int): The server port if establishing a new socket
            **src_port (int): Optional source port to use
            **cid (int): The context/session ID (default 1)
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    def receive_message_udp(self, cid: int = 1, **kwargs) -> 'bytes|MtMessage':
        """Get MT/downlink data received over UDP.
        
        Args:
            **cid (int): Context/session ID
            **urc (str): URC output including hex payload
            **size (int): Maximum bytes to read (default 256)
            **payload_only (bool): Default True returns bytes.
                False returns MtMessage with IP metadata.
        
        Returns:
            `bytes` by default or a `MtMessage` structure with metadata
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    def ntp_sync(self, server: str, **kwargs) -> bool:
        """Synchronize modem time to NTP"""
        raise NotImplementedError('Requires module-specific subclass')
    
    def dns_get(self, cid: int = 1) -> 'list[str]':
        """Get the DNS server address(es)."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def dns_set(self, primary: str, **kwargs) -> bool:
        """Set the DNS server address(es).
        
        Args:
            primary (str): The primary DNS server
            **cid (int): The context ID
            **secondary (str): Optional secondary DNS server
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    def report_debug(self, add_commands: 'list[str]|None' = None) -> None:
        """Log a set of module-relevant config settings and KPIs."""
        debug_commands = [   # Base commands are 3GPP TS 27.007
            'ATI',   # module information
            'AT+CGMR',   # firmware/revision
            'AT+CIMI',   # IMSI
            'AT+CGSN=1',   # IMEI
            'AT+CFUN?',   # Module radio function configured
            'AT+CEREG?',   # Registration status and URC config
            'AT+CGDCONT?',   # PDP/PDN Context configuration
            'AT+CGPADDR?',   # IP address assigned by network
            'AT+CPSMS?',   # Power saving mode settings (requested)
            'AT+CEDRXS?',   # eDRX settings (requested)
            'AT+CEDRXRDP',   # eDRX dynamic parameters
            'AT+CRTDCP?',   # Reporting of terminating data via control plane
            'AT+CSCON?',   # Signalling connection status
            'AT+CESQ',   # Signal quality including RSRQ indexed from 0 = -19.5 in 0.5dB increments, RSRP indexed from 0 = -140 in 1 dBm increments
        ]
        if (isinstance(add_commands, list) and
            all(isinstance(item, str) for item in add_commands)):
            debug_commands += add_commands
        for cmd in debug_commands:
            res = self.send_command(cmd, 15)
            if res == AtErrorCode.OK:
                _log.info('%s => %s', cmd, dprint(self.get_response()))
            else:
                _log.error('Failed to query %s (ErrorCode: %d)', cmd, res)
    
    def get_signal_quality(self) -> SignalQuality:
        """Get a qualitative indicator of 0..5 of satellite signal."""
        sinr = self.get_siginfo().sinr
        if sinr >= SignalLevel.INVALID.value:
            return SignalQuality.WARNING
        if sinr >= SignalLevel.BARS_5.value:
            return SignalQuality.STRONG
        if sinr >= SignalLevel.BARS_4.value:
            return SignalQuality.GOOD
        if sinr >= SignalLevel.BARS_3.value:
            return SignalQuality.MID
        if sinr >= SignalLevel.BARS_2.value:
            return SignalQuality.LOW
        if sinr >= SignalLevel.BARS_1.value:
            return SignalQuality.WEAK
        return SignalQuality.NONE


# Externally callable helper
def get_model(serial: AtClient) -> ModuleModel:
    """Queries a modem to determine its make/model"""
    if serial.send_at_command('ATI', timeout=3) == AtErrorCode.OK:
        res = serial.get_response()
        if 'quectel' in res.lower():
            if 'cc660' in res.lower():
                return ModuleModel.CC660D
            if 'bg95' in res.lower():
                return ModuleModel.BG95
        elif 'murata' in res.lower():
            if '1sc' in res.lower():
                return ModuleModel.TYPE1SC
        elif 'HL781' in res:
            return ModuleModel.HL781X
        _log.warning('Unsupported model: %s', res)
        return ModuleModel.UNKNOWN
    raise OSError('Unable to get modem information')


def is_valid_hostname(hostname) -> bool:
    """Validates a FQDN hostname"""
    if len(hostname) > 255:
        return False
    if hostname[-1] == '.':
        hostname = hostname[:-1]
    allowed = re.compile('(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split('.'))


def is_valid_ip(addr: str) -> bool:
    """Validates an IP address string."""
    try:
        ipaddress.ip_address(addr)
        return True
    except ValueError:
        return False
