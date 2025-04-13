"""Abstraction of the modem interface."""

import ipaddress
import logging
import os
import re
import time

from abc import ABC, abstractmethod
from pyatcommand import AtClient, AtErrorCode, AtTimeout
from pyatcommand.constants import AT_TIMEOUT
from pyatcommand.utils import dprint

from .constants import (
    Chipset,
    ModuleManufacturer,
    ModuleModel,
    PdpType,
    RegistrationState,
    SignalLevel,
    SignalQuality,
    UrcType,
    RadioAccessTechnology,
    RrcState,
)
from .nbntndataclasses import (
    EdrxConfig,
    MoMessage,
    MtMessage,
    NtnLocation,
    PdpContext,
    PsmConfig,
    RegInfo,
    SigInfo,
    SocketStatus,
)
from .ntninit import NtnInitSequence, default_init

__all__ = [
    'NbntnBaseModem',
    'DefaultModem',
    'get_model',
    'is_valid_hostname',
    'is_valid_ip',
]

_log = logging.getLogger(__name__)

_sentinel = object()


class NbntnBaseModem(ABC):
    """Abstract Base Class for a NB-NTN modem."""

    _manufacturer: ModuleManufacturer = ModuleManufacturer.UNKNOWN
    _model: ModuleModel = ModuleModel.UNKNOWN
    _chipset: Chipset = Chipset.UNKNOWN
    _ignss: bool = False   # modem has internal GNSS
    _ntn_only: bool = False   # modem supports only NTN
    _rrc_ack: bool = False   # modem supports RRC send confirmation

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
        self._serial_port = kwargs.pop('port', os.getenv('SERIAL_PORT',
                                                         '/dev/ttyUSB0'))
        self._baudrate = kwargs.pop('baudrate', int(os.getenv('SERIAL_BAUDRATE',
                                                              115200)))
        self._serial: AtClient = kwargs.pop('client', AtClient())
        if not isinstance(self._serial, AtClient):
            raise ValueError('Invalid AtClient')
        self._pdp_type: PdpType = kwargs.pop('pdp_type', PdpType.NON_IP)
        if not isinstance(self._pdp_type, PdpType):
            raise ValueError('Invalid PdpType')
        self._apn: str = ''
        self.apn = kwargs.get('apn', '')
        self._udp_server: str = ''
        self._udp_server_port: int = 0
        for k, v in kwargs.items():
            if (getattr(self, k, None) is not None and
                not callable(getattr(self, k)) and
                not k.startswith('_') and
                v is not None):
                setattr(self, k, v)
        self._command_timeout: float = AT_TIMEOUT   # modem-specific default
    
    def get_at_client(self) -> AtClient:
        """Get the AtClient interface"""
        return self._serial
    
    def connect(self, **kwargs) -> None:
        """Connect to the modem UART/serial.

        Supports PySerial creation kwargs.
        
        Args:
            **port (str): The serial port name (default `/dev/ttyUSB0`)
            **baudrate (int): The serial port baudrate (default `115200`)
        """
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

    def send_command(self, at_command: str, timeout: 'float|None' = _sentinel) -> AtErrorCode:
        """Send an arbitrary AT command and get the result code.
        
        Response values are obtained from a follow-up `get_response()`
        
        Args:
            at_command (str): The AT command to send.
            timeout (float|None): The maximum time to wait for a result in
                seconds. `None` returns immediately with `AtErrorCode.PENDING`.
                Default uses the `_command_timeout` attribute or the environment
                value `AT_TIMEOUT` (default 0.3).
            
        Returns:
            `AtErrorCode`
        """
        if timeout is _sentinel:
            timeout = self._command_timeout
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
    
    def get_cme_mode(self) -> int:
        """Get the CME device error response configuration"""
        if self.send_command('AT+CMEE?') == AtErrorCode.OK:
            return int(self.get_response())
        return 0
    
    def set_cme_mode(self, mode: int) -> bool:
        """Set the CME device error response configuration"""
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
        if self.send_command('AT+CGPADDR') == AtErrorCode.OK:
            res = self.get_response('+CGPADDR:').split('\n')
            if len(res) > 1:
                _log.warning('%d IP addresses returned', len(res))
            ip_address = res[0].split(',')[-1]
            if not is_valid_ip(ip_address):
                ip_address = ''
        if not ip_address and self.send_command('AT+CGDCONT?') == AtErrorCode.OK:
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
        if (not isinstance(server, str) or
            (not is_valid_ip(server) and not is_valid_hostname(server))):
            raise ValueError('Invalid server IP or DNS')
        self._udp_server = server
    
    @property
    def udp_server_port(self) -> int:
        return self._udp_server_port
    
    @udp_server_port.setter
    def udp_server_port(self, port: int):
        if not isinstance(port, int) or port not in range(0, 65536):
            raise ValueError('Invalid UDP port')
        self._udp_server_port = port
    
    @abstractmethod
    def is_asleep(self) -> bool:
        """Check if the modem is in deep sleep state."""
        raise NotImplementedError('Requires module-specific subclass')
    
    @abstractmethod
    def get_sleep_mode(self):
        """Get the modem hardware sleep settings."""
        raise NotImplementedError('Requires module-specfic subclass')

    @abstractmethod
    def set_sleep_mode(self):
        """Set the modem hardware sleep settings."""
        raise NotImplementedError('Requires module-specfic subclass')

    def get_imsi(self) -> 'str':
        """Get the IMSI of the SIM installed with the modem."""
        if self.send_command('AT+CIMI', 5) == AtErrorCode.OK:
            return self.get_response()
        return ''
    
    @abstractmethod
    def initialize_ntn(self, **kwargs) -> bool:
        """Execute the modem-specific initialization to communicate on NTN."""
        ntn_init: 'NtnInitSequence' = kwargs.get('ntn_init', default_init)
        if not isinstance(ntn_init, NtnInitSequence):
            try:
                ntn_init = NtnInitSequence.from_list_of_dict(ntn_init)
            except Exception as exc:
                raise ValueError('Invalid NtnInitSequence') from exc
        if len(ntn_init) == 0:
            raise ValueError('No initialization steps configured')
        sequence_step = 0
        step_success = False
        for step in ntn_init:
            sequence_step += 1
            if step.delay:
                time.sleep(step.delay)
            if step.gpio:
                if step.cmd:
                    _log.debug('GPIO found. Skipping: %s', step.cmd)
                if callable(step.gpio.callback):
                    _log.debug('NTN initialization triggering GPIO callback')
                    step.gpio.callback(step.gpio.duration)
                    time.sleep(step.gpio.duration)
                continue
            if (step.cmd is None or (step.res is None and step.urc is None)):
                _log.warning('Skipping invalid init command (step %d)',
                             sequence_step)
                continue
            at_cmd = step.cmd
            attempt = 1
            if '<pdn_type>' in at_cmd:
                pdn_type = self._pdp_type.name.replace('_', '-')
                at_cmd = at_cmd.replace('<pdn_type>', pdn_type)
            if '<apn>' in at_cmd:
                if not self._apn:
                    _log.warning('No APN configured - UE will not register')
                at_cmd = at_cmd.replace('<apn>', self._apn)
            step_success = False
            while not step_success:
                try:
                    if step.timeout == AT_TIMEOUT:
                        step.timeout = self._command_timeout
                    res = self.send_command(at_cmd, timeout=step.timeout)
                    if step.res is None or res == step.res:
                        step_success = True
                    else:
                        raise ValueError(f'Expected {step.res.name} but got {res.name}')
                except (AtTimeout, ValueError) as exc:
                    err_msg = f'Failed attempt {attempt} to {step.why}: '
                    if isinstance(exc, AtTimeout):
                        err_msg += f'timeout ({at_cmd})'
                    else:
                        err_msg += str(exc)
                    _log.error(err_msg)
                    if step.retry:
                        if step.retry.count > 0:
                            if attempt >= step.retry.count:
                                break   # while not step_success loop
                            if step.retry.delay:
                                _log.warning('Init retry %s in %0.1f seconds',
                                             step.cmd, step.retry.delay)
                                time.sleep(step.retry.delay)
                        attempt += 1
                    else:
                        break   # while not step_success loop
            if not step_success:
                break   # step loop
            if self._serial.is_response_ready():   # clear response for next step
                init_res = self._serial.get_response()
                if init_res:
                    _log.debug('%s: %s', step.why or 'NTN init', init_res)
            if step.urc:
                expected = step.urc.urc
                urc_kwargs = { 'prefixes': ['+', '%'] }
                if step.urc.timeout:
                    urc_kwargs['timeout'] = step.urc.timeout
                urc = self.await_urc(expected, **urc_kwargs)
                if urc != expected:
                    _log.error('Received %s but expected %s', urc, expected)
                    break   # step loop
                step_success = True
        if sequence_step != len(ntn_init):
            _log.error('NTN initialization failed at step %d (%s)',
                       sequence_step, ntn_init[sequence_step - 1].cmd)
            return False
        _log.debug('NTN initialization complete')
        return True
    
    def await_urc(self, urc: str = '', **kwargs) -> str:
        """Wait for an unsolicited result code or timeout.
        
        Args:
            **timeout (float): Maximum time in seconds to wait for URC.
            **prefixes (list[str]): Additional URC prefixes to consider.
        
        Returns:
            The awaited URC or an empty string if it timed out.
        """
        timeout = float(kwargs.get('timeout', 0))
        _log.debug('Waiting for unsolicited %s (timeout: %s)', urc, timeout)
        prefixes = kwargs.get('prefixes', ['+', '%'])
        wait_start = time.time()
        while timeout == 0 or time.time() - wait_start < timeout:
            if self.check_urc(prefixes=prefixes):
                candidate = self.get_response()
                if urc and candidate.startswith(urc):
                    _log.debug('URC: %s received after %0.1f seconds',
                               candidate, time.time() - wait_start)
                    return candidate
            else:
                time.sleep(1)
        _log.warning('Timed out waiting for URC (%s)', urc)
        return ''
    
    def parse_urc(self, urc: str) -> dict:
        """Parse a URC to retrieve relevant metadata."""
        raise NotImplementedError('Requires module-specfic subclass')
    
    def get_info(self) -> str:
        """Get the detailed response of the AT information command."""
        if self.send_command('ATI', timeout=3) == AtErrorCode.OK:
            return self.get_response()
        return ''
    
    def get_imei(self) -> str:
        """Get the modem's IMEI number.
        
        International Mobile Equipment Identity
        """
        if self.send_command('AT+CGSN') == AtErrorCode.OK:
            return self.get_response()
        return ''
    
    def enable_radio(self, enable: bool = True, **kwargs) -> bool:
        """Enable or disable the radio.
        
        Some radios may take several seconds to respond.
        
        Args
            enable (bool): The setting to apply.
            **timeout (float): Optional timeout if non-default.
        """
        cmd = f'AT+CFUN={int(enable)}'
        return self.send_command(cmd, **kwargs) == AtErrorCode.OK
    
    def use_ignss(self, enable: bool = True, **kwargs) -> bool:
        """Use the internal GNSS for NTN network registration."""
        raise NotImplementedError('Requires module-specfic subclass')
    
    def supported_rat(self) -> 'list[RadioAccessTechnology]':
        """Get the list of supported Radio Access Technologies of the modem."""
        return [RadioAccessTechnology.NBNTN]
        
    def get_rat(self) -> RadioAccessTechnology:
        """Get the current Radio Access Technology."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def set_rat(self, rat: RadioAccessTechnology = RadioAccessTechnology.NBNTN):
        """Set the Radio Access Technology to use."""
        raise NotImplementedError('Requires module-specific subclass')

    @abstractmethod
    def get_location(self) -> 'NtnLocation|None':
        """Get the location currently in use by the modem."""
        raise NotImplementedError('Requires module-specific subclass')
    
    @abstractmethod
    def set_location(self, loc: NtnLocation, **kwargs) -> bool:
        """Set the modem location to use for registration/TAU."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def get_reginfo(self, urc: str = '') -> RegInfo:
        """Get the parameters of the registration state of the modem.
        
        Parses the 3GPP standard `+CEREG` response/URC.
        
        Args:
            urc (str): Optional URC will be queried if not provided.
        
        Returns:
            RegInfo registration metadata.
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
                    info.act_t3324_bitmask = param
                elif i == 7 and param:
                    info.tau_t3412_bitmask = param
        return info
    
    def get_regconfig(self) -> int:
        """Get the registration URC reporting configuration."""
        if self.send_command('AT+CEREG?') == AtErrorCode.OK:
            config = self.get_response('+CEREG:').split(',')[0]
            return int(config)
        return -1
    
    def set_regconfig(self, config: int) -> bool:
        """Set the registration URC verbosity."""
        if config not in range(0, 6):
            raise ValueError('Invalid CEREG config value')
        return self.send_command(f'AT+CEREG={config}') == AtErrorCode.OK
    
    def get_rrc_state(self) -> RrcState:
        """Get the perceived radio resource control connection status."""
        if self.send_command('AT+CSCON?') == AtErrorCode.OK:
            return RrcState(int(self.get_response('+CSCON:').split(',')[1]))
        return RrcState.UNKNOWN

    def enable_rrc_urc(self, enable: bool = True) -> bool:
        """Enable or disable RRC state change notifications."""
        return self.send_command(f'AT+CSCON={int(enable)}') == AtErrorCode.OK
    
    @abstractmethod
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
    
    def get_signal_quality(self, sinr: 'int|float|None' = None) -> SignalQuality:
        """Get a qualitative indicator of 0..5 of satellite signal."""
        if not isinstance(sinr, (int, float)):
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
        """Get the Power Save Mode settings.
        
        Returns the configured/requested settings, which may not be granted.
        For granted/actual, use `RegInfo.get_psm_granted()`
        """
        config = PsmConfig()
        if self.send_command('AT+CPSMS?') == AtErrorCode.OK:
            psm_parts = self.get_response('+CPSMS:').split(',')
            for i, param in enumerate(psm_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 0:
                    config.enabled = param == '1'
                if i == 3:
                    config.tau_t3412_bitmask = param
                elif i == 4:
                    config.act_t3324_bitmask = param
        return config
    
    def set_psm_config(self, psm: 'PsmConfig|None' = None) -> bool:
        """Configure requested Power Saving Mode settings.
        
        The configured values are requested but not necessarily granted by the
        network during registration/TAU.
        
        Args:
            psm (PsmConfig): The requested PSM configuration.
        """
        if psm and not isinstance(psm, PsmConfig):
            raise ValueError('Invalid PSM configuration')
        mode = 0 if psm is None else 1
        cmd = f'AT+CPSMS={mode}'
        if mode > 0:
            cmd += f',{psm.tau_t3412_bitmask},{psm.act_t3324_bitmask}'
        return self.send_command(cmd) == AtErrorCode.OK

    def get_edrx_config(self) -> EdrxConfig:
        """Get the Extended Discontinuous Receive (eDRX) mode settings.
        
        Returns the configured/requested values, which may not be granted.
        To determine granted/actual values use `get_edrx_dynamic()`
        """
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
        """Configure requested Extended Discontinuous Receive (eDRX) settings.
        
        The requested values may not be granted by the network.
        
        Args:
            edrx (EdrxConfig): The requested eDRX configuration.
        """
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
        # TODO: deprecate in favour of restrict_ntn_lband
        raise NotImplementedError('Requires module-specific subclass')
        
    @abstractmethod
    def get_band(self) -> int:
        """Get the current LTE band in use."""
        _log.warning('No module-specific subclass - returning -1')
        return -1

    @abstractmethod
    def restrict_ntn_lband(self, restrict: bool = True) -> bool:
        """Restrict (or unrestrict) NTN to L-band 255."""
        raise NotImplementedError('Requires module-specific subclass')

    @abstractmethod
    def get_frequency(self) -> int:
        """Get the current frequency (EARFCN) in use if camping on a cell."""
        _log.warning('No module-specific subclass - returning -1')
        return -1
    
    @abstractmethod
    def get_urc_type(self, urc: str) -> UrcType:
        """Get the URC type to determine a handling function/parameters."""
        if not isinstance(urc, str):
            raise ValueError('Invalid URC - must be string type')
        if urc.startswith('+CEREG:'):
            return UrcType.REGISTRATION
        if urc.startswith('+CRTDCP:'):
            return UrcType.NIDD_MT_RCVD
        if urc.startswith('+CSCON:'):
            return UrcType.RRC_STATE
        return UrcType.UNKNOWN

    def inject_urc(self, urc: str) -> bool:
        """Injects a URC string into the AtClient unsolicited queue.
        
        Used for custom events e.g. message send complete without native URC.
        """
        if not urc.startswith('\r\n') or not urc.endswith('\r\n'):
            _log.warning('URC injection without header/trailer')
        else:
            _log.debug('Injecting URC: %s', dprint(urc))
        self._serial._unsolicited_queue.put(urc)
    
    def get_last_error(self, **kwargs) -> int:
        """Get the error code of the prior errored command.
        
        Keyword args allow modem-specific parameters.
        
        Args:
            failed_op (str): The type of operation that failed.
        
        Returns:
            An error code specific to the manufacturer/module. -1 is unknown.
            
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    @abstractmethod
    def enable_nidd_urc(self, enable: bool = True, **kwargs) -> bool:
        """Enable unsolicited reporting of received Non-IP data.
        
        Message data is exchanged via control plane.
        Keyword arguments allow modem-specific options.
        
        Args:
            enable (bool): Enable or disable URC reports for NIDD messages.
        """
        return self.send_command(f'AT+CRTDCP={int(enable)}') == AtErrorCode.OK

    @abstractmethod
    def send_message_nidd(self, message: bytes, cid: int = 1, **kwargs) -> 'MoMessage|None':
        """Send a message using Non-IP Data Delivery.
        
        Keyword arguments allows for device-specific parameters.
        
        Args:
            message (bytes): The message content/payload.
            cid (int): The (PDP/PDN) context ID to use.
            **rai (int): Release Assistance Indicator none (0),
                done on tx (1), done on rx (2)
            **data_type (int): Regular (0) or Exception (1)
        
        Returns:
            MoMessage object with optional metadata, or None if it could not
                be sent.
        """
        _log.debug('Sending NIDD message without confirmation')
        cmd = f'AT+CSODCP={cid},{len(message)},"{message.hex()}"'
        rai = kwargs.get('rai')
        data_type = kwargs.get('data_type')
        if rai:
            cmd += f',{rai}'
        if data_type:
            if rai is None:
                cmd += ','
            cmd += f',{data_type}'
        if self.send_command(cmd) == AtErrorCode.OK:
            return MoMessage(message, PdpType.NON_IP)
        return None
    
    @abstractmethod
    def receive_message_nidd(self, urc: str, **kwargs) -> 'bytes|MtMessage|None':
        """Parses a NIDD URC string to derive the MT/downlink bytes sent.
        
        Args:
            urc (str): The 3GPP standard +CRTDCP unsolicited output
            **include_meta (bool): If True returns `MtMessage`
        
        Returns:
            The payload `bytes` or `MtMessage` metadata with `payload`
        """
        payload = None
        if isinstance(urc, str) and urc.startswith('+CRTDCP'):
            urc = urc.replace('+CRTDCP:', '').strip()
            params = urc.split(',')
            for i, param in enumerate(params):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 2:
                    payload = bytes.fromhex(param)
        else:
            _log.error('Invalid URC: %s', urc)
        if kwargs.get('include_meta', False) is True:
            return MtMessage(payload, transport=PdpType.NON_IP)
        return payload
    
    @abstractmethod
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
    
    @abstractmethod
    def enable_udp_urc(self, enable: bool = True, **kwargs) -> bool:
        """Enables URC supporting UDP operation."""
        # raise NotImplementedError('Must implement in subclass')
        return False
    
    @abstractmethod
    def udp_socket_open(self, **kwargs) -> bool:
        """Open a UDP socket.
        
        Args:
            **server (str): The server IP or URL
            **port (int): The destination port of the server
            **cid (int): The context/session ID (default 1)
            **src_port (int): Optional source port to use when sending
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    @abstractmethod
    def udp_socket_status(self, cid: int = 1) -> SocketStatus:
        """Get the status of the specified socket/context ID."""
        raise NotImplementedError('Requires module-specific subclass')
    
    @abstractmethod
    def udp_socket_close(self, cid: int = 1) -> bool:
        """Close the specified socket."""
        raise NotImplementedError('Requires module-specific subclass')
    
    @abstractmethod
    def send_message_udp(self, message: bytes, **kwargs) -> 'MoMessage|None':
        """Send a message using UDP transport.

        Opens a socket if one does not exist and closes after sending.
        
        Args:
            message (bytes): The binary blob to be sent
            **server (str): The server IP or URL if establishing a new socket
            **port (int): The server port if establishing a new socket
            **src_port (int): Optional source port to use
            **cid (int): The context/session ID (default 1)
        
        Returns:
            A `MoMessage` structure with `payload` and IP header metadata
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    @abstractmethod
    def receive_message_udp(self, cid: int = 1, **kwargs) -> 'bytes|MtMessage|None':
        """Get MT/downlink data received over UDP.
        
        Args:
            cid (int): Context/session ID (default 1)
            **urc (str): URC output including hex payload
            **size (int): Maximum bytes to read (default 256)
            **include_meta (bool): If True returns `MtMessage` otherwise returns
                `bytes`.
        
        Returns:
            `bytes` by default or a `MtMessage` structure with `payload` and
                IP address/port, or `None` if no data was received
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
    
    @abstractmethod
    def report_debug(self,
                     add_commands: 'list[str]|None' = None,
                     replace: bool = False) -> None:
        """Log a set of module-relevant config settings and KPIs.
        
        Args:
            add_commands (list): A list of additional AT commands to send.
            replace (bool): If True, replaces the default 3GPP command list.
        """
        debug_commands = [   # Base commands are 3GPP TS 27.007
            'ATI',   # module information
            'AT+CGMR',   # firmware/revision
            'AT+CIMI',   # IMSI
            'AT+CGSN',   # IMEI
            'AT+CFUN?',   # Module radio function configured
            'AT+CEREG?',   # Registration status and URC config
            'AT+CGDCONT?',   # PDP/PDN Context configuration
            'AT+CGPADDR',   # IP address(es) assigned by network
            'AT+CPSMS?',   # Power saving mode settings (requested)
            'AT+CEDRXS?',   # eDRX settings (requested)
            'AT+CEDRXRDP',   # eDRX dynamic parameters
            'AT+CRTDCP?',   # Reporting of terminating data via control plane
            'AT+CSCON?',   # Signalling connection status
            'AT+CESQ',   # Signal quality including RSRQ indexed from 0 = -19.5 in 0.5dB increments, RSRP indexed from 0 = -140 in 1 dBm increments
        ]
        if (isinstance(add_commands, list) and
            all(isinstance(item, str) for item in add_commands)):
            if replace is True:
                debug_commands = []
            debug_commands += add_commands
        for cmd in debug_commands:
            res = self.send_command(cmd, 15)
            if res == AtErrorCode.OK:
                _log.info('%s => %s', cmd, dprint(self.get_response()))
            else:
                _log.error('Failed to query %s (ErrorCode: %d)', cmd, res)


class DefaultModem(NbntnBaseModem):
    """A generic modem supporting the basic 3GPP AT commands."""
    
    def initialize_ntn(self, **kwargs):
        return super().initialize_ntn(**kwargs)
    
    def get_sleep_mode(self):
        return super().get_sleep_mode()
    
    def set_sleep_mode(self):
        return super().set_sleep_mode()
    
    def is_asleep(self):
        return super().is_asleep()
    
    def get_location(self):
        return super().get_location()
    
    def set_location(self, loc, **kwargs):
        return super().set_location(loc, **kwargs)
    
    def get_siginfo(self):
        return super().get_siginfo()
    
    def get_band(self):
        return super().get_band()
    
    def restrict_ntn_lband(self, restrict: bool = True):
        return super().restrict_ntn_lband(restrict)
    
    def get_frequency(self):
        return super().get_frequency()
    
    def get_urc_type(self, urc):
        return super().get_urc_type(urc)
    
    def enable_nidd_urc(self, enable = True, **kwargs):
        return super().enable_nidd_urc(enable, **kwargs)
    
    def send_message_nidd(self, message, cid = 1, **kwargs):
        return super().send_message_nidd(message, cid, **kwargs)
    
    def receive_message_nidd(self, urc, **kwargs):
        return super().receive_message_nidd(urc, **kwargs)
    
    def ping_icmp(self, **kwargs):
        return super().ping_icmp(**kwargs)
    
    def enable_udp_urc(self, enable = True, **kwargs):
        return super().enable_udp_urc(enable, **kwargs)
    
    def udp_socket_open(self, **kwargs):
        return super().udp_socket_open(**kwargs)
    
    def udp_socket_status(self, cid = 1):
        return super().udp_socket_status(cid)
    
    def udp_socket_close(self, cid = 1):
        return super().udp_socket_close(cid)
    
    def send_message_udp(self, message, **kwargs):
        return super().send_message_udp(message, **kwargs)
    
    def receive_message_udp(self, cid = 1, **kwargs):
        return super().receive_message_udp(cid, **kwargs)
    
    def report_debug(self, add_commands = None, replace = False):
        return super().report_debug(add_commands)


# Externally callable helper
def get_model(serial: AtClient) -> ModuleModel:
    """Queries a modem to determine its make/model"""
    if serial.send_at_command('ATI', timeout=3) == AtErrorCode.OK:
        res = serial.get_response()
        if 'quectel' in res.lower():
            if 'cc660' in res.lower():
                return ModuleModel.CC660D
            if 'bg95' in res.lower():
                return ModuleModel.BG95S5
            if 'bg770' in res.lower():
                return ModuleModel.BG770ASN
        elif 'murata' in res.lower():
            if '1sc' in res.lower():
                return ModuleModel.TYPE1SC
        elif 'HL781' in res:
            return ModuleModel.HL781X
        elif 'telit' in res.lower():
            if 'ME910G1' in res:
                return ModuleModel.ME910G1
        _log.warning('Unsupported model: %s', res)
        return ModuleModel.UNKNOWN
    raise OSError('Unable to get modem information')


def is_valid_hostname(hostname) -> bool:
    """Validates a FQDN hostname"""
    if len(hostname) > 255:
        return False
    if hostname[-1] == '.':
        hostname = hostname[:-1]
    allowed = re.compile(r'(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split('.'))


def is_valid_ip(addr: str) -> bool:
    """Validates an IP address string."""
    try:
        ipaddress.ip_address(addr)
        return True
    except ValueError:
        return False
