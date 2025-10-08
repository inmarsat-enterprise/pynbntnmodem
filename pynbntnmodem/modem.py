"""Abstraction of the NB-NTN modem interface."""

import logging
import time
from abc import ABC
from typing import Any, Optional

from pyatcommand import AtClient, AtResponse, AtTimeout
from pyatcommand.common import dprint

from .constants import (
    CeregMode,
    Chipset,
    ModuleManufacturer,
    ModuleModel,
    PdnType,
    RadioAccessTechnology,
    RegistrationState,
    RrcState,
    SignalLevel,
    SignalQuality,
    UrcType,
)
from .ntninit import NtnInitSequence, default_init
from .structures import (
    EdrxConfig,
    MoMessage,
    MtMessage,
    NtnLocation,
    PdnContext,
    PsmConfig,
    RegInfo,
    SigInfo,
    SocketStatus,
)
from .utils import is_valid_hostname, is_valid_ip

_log = logging.getLogger(__name__)


class NbntnModem(AtClient, ABC):
    """Abstract Base Class for a NB-NTN modem."""
    
    # sub/class fixed attributes
    _manufacturer: ModuleManufacturer = ModuleManufacturer.UNKNOWN
    _model: ModuleModel = ModuleModel.UNKNOWN
    _chipset: Chipset = Chipset.UNKNOWN
    _ignss: bool = False   # modem has internal GNSS
    _ntn_only: bool = False   # modem supports only NTN
    _rrc_ack: bool = False   # modem supports RRC send confirmation
    _command_timeout: float|None = None   # module-specific heuristic

    def __init__(self, **kwargs) -> None:
        """Instantiate the class.
        
        Args:
            **port (str): default to .env `SERIAL_PORT`
            **baudrate (int): default to .env `SERIAL_BAUDRATE`
            **pdn_type (PdpType): default `NON_IP`
            **apn (str): The APN value to use
            **udp_server (str): Optional UDP destination server
            **udp_server_port (int): Optional UDP destination port
        """
        kwargs['baudrate'] = kwargs.pop('baudrate', 115200)
        super().__init__(**kwargs)
        self._command_timeout = 1
        self._version: str = ''
        self._imsi: str = ''
        self._imei: str = ''
        self._pdn_type: PdnType = PdnType.NON_IP
        self._apn: str = ''
        self._udp_server: str = ''
        self._udp_server_port: int = 0
        self._ntn_initialized: bool = False
        for k, v in kwargs.items():
            if k in ['pdn_type', 'apn', 'udp_server', 'udp_server_port']:
                setattr(self, k, v)
        self._debug_commands: list[str] = [
            'AT+CMEE?',   # Enhanced error output
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

    def _post_mutate(self, **kwargs):
        """Call post-mutation to a subclass of NbntnModem."""
        self._ntn_initialized = False
        
    def connect(self, **kwargs) -> None:
        return super().connect(**kwargs)
    
    def disconnect(self) -> None:
        reset_props = ['version', 'imei', 'imsi']
        for prop in reset_props:
            if hasattr(self, f'_{prop}'):
                setattr(self, f'_{prop}', '')
        return super().disconnect()
    
    @property
    def manufacturer(self) -> str:
        if self._manufacturer.name == 'UNKNOWN' and self.is_connected():
            res = self.send_command('AT+CGMI')
            if res.ok and res.info:
                return res.info.split(' ')[0].upper()
        return self._manufacturer.name
    
    @property
    def model(self) -> str:
        if self._model == ModuleModel.UNKNOWN and self.is_connected():
            res = self.send_command('AT+CGMM')
            if res.ok and res.info:
                return res.info
        return self._model.name
    
    @property
    def chipset(self) -> str:
        return self._chipset.name
    
    @property
    def firmware_version(self) -> str:
        if not self._version:
            res = self.send_command('AT+CGMR')
            if res.ok and res.info:
                return res.info
        return self._version
    
    @property
    def has_ignss(self) -> bool:
        return self._ignss
    
    @property
    def ntn_only(self) -> bool:
        return self._ntn_only
    
    @property
    def pdn_type(self) -> PdnType:
        return self._pdn_type
    
    @pdn_type.setter
    def pdn_type(self, pdn_type: PdnType):
        if not isinstance(pdn_type, PdnType):
            raise ValueError('Invalid PDP Type')
        self._pdn_type = pdn_type

    @property
    def imei(self) -> str:
        if not self._imei:
            res = self.send_command('AT+CGSN')
            if res.ok and res.info:
                self._imei = res.info
        return self._imei
    
    @property
    def imsi(self) -> str:
        if not self._imsi:
            res = self.send_command('AT+CIMI')
            if res.ok and res.info:
                self._imsi = res.info
        return self._imsi
    
    @property
    def apn(self) -> str:
        if not self._apn and self.is_connected():
            res = self.send_command('AT+CGDCONT?', prefix='+CGDCONT:')
            if res.ok and res.info:
                contexts = res.info.split('\n')
                return contexts[0].split(',')[2].replace('"', '')
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
    
    @property
    def ip_address(self) -> str:
        ip_address = ''
        res = self.send_command('AT+GCPADDR')
        if res.ok and res.info:
            ip_addresses = res.info.split('\n')
            if len(ip_address) > 1:
                _log.warning('%d IP addresses returned', len(ip_addresses))
            ip_address = ip_addresses[0].split(',')[-1]
            if not is_valid_ip(ip_address):
                ip_address = ''
        if not ip_address:
            res = self.send_command('AT+CGDCONT?')
            if res.ok and res.info:
                params = res.info.split(',')
                for i, param in enumerate(params):
                    param = param.replace('"', '')
                    if not param:
                        continue
                    if i == 3:
                        ip_address = param
        return ip_address

    @property
    def ntn_initialized(self) -> bool:
        return self._ntn_initialized
    
    def get_model(self) -> ModuleModel:
        res = self.send_command('ATI', timeout=3)
        if res.ok and res.info:
            if 'quectel' in res.info.lower():
                if 'cc660' in res.info.lower():
                    return ModuleModel.CC660D
                if 'bg95' in res.info.lower():
                    return ModuleModel.BG95S5
                if 'bg770' in res.info.lower():
                    return ModuleModel.BG770ASN
            elif 'murata' in res.info.lower():
                if '1sc' in res.info.lower():
                    return ModuleModel.TYPE1SC
            elif 'HL781' in res.info:
                return ModuleModel.HL781X
        elif not res.ok:
            res = self.send_command('AT+CGMM')
            if res.ok and res.info:
                if 'nrf9151' in res.info.lower():
                    return ModuleModel.NRF9151
        _log.warning('Unable to determine model: %s',
                     res.info if res.info else 'UNKNOWN')
        return ModuleModel.UNKNOWN

    def get_cme_mode(self) -> int:
        """Get the CME device error response configuration"""
        res: AtResponse = self.send_command('AT+CMEE?')
        if res.ok and res.info:
            return int(res.info)
        return 0

    def set_cme_mode(self, mode: int) -> bool:
        """Set the CME device error response configuration"""
        if mode not in [0, 1, 2]:
            raise ValueError('Invalid CMEE setting')
        res: AtResponse = self.send_command(f'AT+CMEE={mode}')
        return res.ok

    def await_urc(self, urc: str = '', **kwargs) -> str:
        """Wait for an unsolicited result code or timeout.
        
        Args:
            **timeout (float): Maximum time in seconds to wait for URC.
        
        Returns:
            The awaited URC or an empty string if it timed out.
        """
        timeout = float(kwargs.get('timeout', 0))
        _log.debug('Waiting for unsolicited %s (timeout: %s)', urc, timeout)
        wait_start = time.time()
        while timeout == 0 or time.time() - wait_start < timeout:
            candidate = self.get_urc()
            if candidate and candidate.startswith(urc):
                _log.debug('URC: %s received after %0.1f seconds',
                            candidate, time.time() - wait_start)
                return candidate
            else:
                time.sleep(0.25)
        _log.warning('Timed out waiting for URC (%s)', urc)
        return ''
    
    def parse_urc(self, urc: str) -> dict:
        """Parse a URC to retrieve relevant metadata."""
        raise NotImplementedError('Requires module-specfic subclass')
    
    def inject_urc(self, urc: str, **kwargs) -> bool:
        """Injects a URC string into the AtClient unsolicited queue.
        
        Used for custom events e.g. message send complete without native URC.
        """
        if not urc.startswith('\r\n') or not urc.endswith('\r\n'):
            _log.warning('URC injection without header/trailer')
        else:
            _log.debug('Injecting URC: %s', dprint(urc))
        try:
            if kwargs.get('split') is True:
                urcs = [u.strip() for u in urc.strip().split('\r\n') if u]
                if len(urcs) > 1:
                    _log.warning('Splitting into %d URC', len(urcs))
                for u in urcs:
                    self._unsolicited_queue.put(u)
            else:
                self._unsolicited_queue.put(urc.strip())
            return True
        except Exception:
            return False
    
    # @abstractmethod
    def initialize_ntn(self, **kwargs) -> bool:
        """Execute the modem-specific initialization to communicate on NTN.
        
        Subclasses should call super() with ntn_init paramter.
        
        Args:
            **ntn_init (NtnInitSequence|dict): The module-specific
                initialization sequence.
        """
        ntn_init: NtnInitSequence = kwargs.get('ntn_init', default_init)
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
                pdn_type = self._pdn_type.name.replace('_', '-')
                at_cmd = at_cmd.replace('<pdn_type>', pdn_type)
            if '<apn>' in at_cmd:
                if not self._apn:
                    _log.warning('No APN configured - UE will not register')
                at_cmd = at_cmd.replace('<apn>', self._apn)
            step_success = False
            while not step_success:
                try:
                    if step.timeout and self._command_timeout:
                        if step.timeout < self._command_timeout:
                            step.timeout = self._command_timeout
                        _log.debug('Waiting up to %0.1fs (%s)',
                                   step.timeout, step.why)
                    res: AtResponse = self.send_command(at_cmd,
                                                        timeout=step.timeout)
                    if step.res is None or res.result == step.res:
                        step_success = True
                    else:
                        raise ValueError(f'Expected {step.res}'
                                         f' but got {res.result}')
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
            if step.urc:
                expected = step.urc.urc
                urc_kwargs: dict = { 'prefixes': ['+', '%'] }
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
        if step_success:
            _log.debug('NTN initialization complete')
        self._ntn_initialized = step_success
        return self._ntn_initialized
    
    def get_info(self, timeout: float = 3) -> str:
        """Get the detailed response of the AT information command."""
        res: AtResponse = self.send_command('ATI', timeout)
        if res.ok and res.info:
            return res.info
        return ''

    def enable_radio(self, enable: bool = True, **kwargs) -> bool:
        """Enable or disable the radio.
        
        Some radios may take several seconds to respond.
        
        Args
            enable (bool): The setting to apply.
            **timeout (float): Optional timeout if non-default.
        """
        cmd = f'AT+CFUN={int(enable)}'
        res = self.send_command(cmd, **kwargs)
        return res.ok

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

    def get_location(self, **kwargs) -> 'NtnLocation|None':
        """Get the location currently in use by the modem."""
        raise NotImplementedError('Requires module-specific subclass')
    
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
            res = self.send_command('AT+CEREG?')
            if res.ok and res.info:
                urc = res.info
        if urc:
            cereg_parts = urc.replace('+CEREG:', '').strip().split(',')
            if (queried):
                config = CeregMode(int(cereg_parts.pop(0)))
                _log.debug('Registration reporting mode: %s', config)
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
    
    def get_regconfig(self) -> CeregMode:
        """Get the registration URC reporting configuration."""
        res = self.send_command('AT+CEREG?', prefix='+CEREG:')
        if res.ok and res.info:
            config = res.info.split(',')[0]
            return CeregMode(int(config))
        return CeregMode.NONE
    
    def set_regconfig(self, config: CeregMode|int) -> bool:
        """Set the registration URC verbosity."""
        if not isinstance(config, CeregMode):
            config = CeregMode(config)
        res = self.send_command(f'AT+CEREG={config.value}')
        return res.ok
    
    def get_rrc_state(self) -> RrcState:
        """Get the perceived radio resource control connection status."""
        res = self.send_command('AT+CSCON?', prefix='+CSCON:')
        if res.ok and res.info:
            return RrcState(int(res.info.split(',')[1]))
        return RrcState.UNKNOWN

    def enable_rrc_urc(self, enable: bool = True) -> bool:
        """Enable or disable RRC state change notifications."""
        res = self.send_command(f'AT+CSCON={int(enable)}')
        return res.ok
    
    # @abstractmethod
    def get_siginfo(self) -> SigInfo:
        """Get the signal information from the modem."""
        info = SigInfo(255, 255, 255, 255)
        res = self.send_command('AT+CESQ', prefix='+CESQ:')
        if res.ok and res.info:
            sig_parts = res.info.split(',')
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

    def get_contexts(self) -> list[PdnContext]:
        """Get the list of configured PDP contexts in the modem."""
        contexts: list[PdnContext] = []
        res = self.send_command('AT+CGDCONT?', prefix='+CGDCONT:')
        if res.ok and res.info:
            context_strs = res.info.split('\n')
            for s in context_strs:
                c = PdnContext()
                for i, param in enumerate(s.split(',')):
                    param = param.replace('"', '')
                    if not param:
                        continue
                    if i == 0:
                        c.id = int(param)
                    elif i == 1:
                        c.pdn_type = PdnType[param.upper().replace('-', '_')]
                    elif i == 2:
                        c.apn = param
                    elif i == 3:
                        c.ip = param
                contexts.append(c)
        res = self.send_command('AT+CGACT?', prefix='+CGACT:')
        if res.ok and res.info:
            context_states = res.info.split('\n')
            for context_state in context_states:
                cid, state = context_state.split(',')
                cid = int(cid)
                active = state == '1'
                for c in contexts:
                    if c.id == cid:
                        c.active = active
        return contexts
    
    def set_context(self, apn: str, pdn_type: PdnType, **kwargs) -> bool:
        """(Re)Define a PDN/PDP context.
        
        Args:
            apn (str): The APN name.
            pdn_type (PdpType): The PDN context type.
            **cid (int): The context ID.
            **reconnect (bool): Optional restart modem after change.
        """
        if not isinstance(apn, str) or not apn:
            raise ValueError('Missing APN value')
        if not isinstance(pdn_type, PdnType):
            raise ValueError('Invalid PDP type')
        cid = kwargs.get('cid', 1)
        reconnect = kwargs.get('reconnect')
        result = False
        if reconnect is True:
            if not self.send_command('AT+CFUN=0', timeout=30).ok:
                _log.error('Disable modem failed')
        pdp_name = pdn_type.name.replace('_', '-')
        cmd = f'AT+CGDCONT={cid},"{pdp_name}","{apn}"'
        result = self.send_command(cmd, timeout=10).ok
        if reconnect is True:
            if not self.send_command('AT+CFUN=1', timeout=30).ok:
                _log.error('Enable modem failed')
            if result and cid == 1:
                self._pdn_type = pdn_type
        return result
    
    def get_psm_config(self) -> PsmConfig:
        """Get the Power Save Mode settings.
        
        Returns the configured/requested settings, which may not be granted.
        For granted/actual, use `RegInfo.get_psm_granted()`
        """
        config = PsmConfig()
        res = self.send_command('AT+CPSMS?', prefix='+CPSMS:')
        if res.ok and res.info:
            psm_parts = res.info.split(',')
            for i, param in enumerate(psm_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 0:
                    config.mode = int(param)
                if i == 3:
                    config.tau_t3412_bitmask = param
                elif i == 4:
                    config.act_t3324_bitmask = param
        return config
    
    def set_psm_config(self, psm: PsmConfig|None = None) -> bool:
        """Configure requested Power Saving Mode settings.
        
        The configured values are requested but not necessarily granted by the
        network during registration/TAU.
        
        Args:
            psm (PsmConfig): The requested PSM configuration.
        """
        if psm and not isinstance(psm, PsmConfig):
            raise ValueError('Invalid PSM configuration')
        mode = 0 if psm is None else psm.mode
        cmd = f'AT+CPSMS={mode}'
        if mode > 0 and isinstance(psm, PsmConfig):
            cmd += f',"{psm.tau_t3412_bitmask}","{psm.act_t3324_bitmask}"'
        res = self.send_command(cmd)
        return res.ok

    def enable_psm_urc(self, enable: bool = True, **kwargs) -> bool:
        """Enable/disable reports of entry or exit of power save mode."""
        raise NotImplementedError('Requires module-specific subclass')
        
    def get_edrx_config(self) -> EdrxConfig:
        """Get the Extended Discontinuous Receive (eDRX) mode settings.
        
        Returns the configured/requested values, which may not be granted.
        To determine granted/actual values use `get_edrx_dynamic()`
        """
        config = EdrxConfig()
        res = self.send_command('AT+CEDRXS?', prefix='+CEDRXS:')
        if res.ok and res.info:
            edrx_parts = res.info.split(',')
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
        if mode > 0 and isinstance(edrx, EdrxConfig):
            cmd += f',5,"{edrx.cycle_bitmask}"'
        res = self.send_command(cmd)
        return res.ok

    def get_edrx_dynamic(self) -> EdrxConfig:
        """Get the eDRX parameters granted by the network."""
        dynamic = EdrxConfig()
        res = self.send_command('AT+CEDRXRDP', prefix='+CEDRXRDP:')
        if res.ok and res.info:
            edrx_parts = res.info.split(',')
            for i, param in enumerate(edrx_parts):
                param = param.replace('"', '')
                if not param:
                    continue
                if i == 2:
                    dynamic.cycle_bitmask = param
                elif i == 3:
                    dynamic.ptw_bitmask = param
        return dynamic
    
    def get_sleep_mode(self) -> Any:
        """Get the modem hardware sleep settings."""
        raise NotImplementedError('Requires module-specfic subclass')

    def set_sleep_mode(self, **kwargs) -> bool:
        """Set the modem hardware sleep settings."""
        raise NotImplementedError('Requires module-specfic subclass')
    
    def is_asleep(self) -> bool:
        """Check if the modem is in deep sleep state."""
        raise NotImplementedError('Requires module-specific subclass')
    
    def get_band(self) -> int:
        """Get the current LTE band in use."""
        _log.warning('No module-specific subclass - returning -1')
        return -1

    def restrict_ntn_lband(self, restrict: bool = True) -> bool:
        """Restrict (or unrestrict) NTN to L-band 255."""
        # raise NotImplementedError('Requires module-specific subclass')
        return False

    def get_frequency(self) -> int:
        """Get the current frequency (EARFCN) in use if camping on a cell."""
        _log.warning('No module-specific subclass - returning -1')
        return -1
    
    # @abstractmethod
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

    # @abstractmethod
    def enable_nidd_urc(self, enable: bool = True, **kwargs) -> bool:
        """Enable unsolicited reporting of received Non-IP data.
        
        Message data is exchanged via control plane.
        Keyword arguments allow modem-specific options.
        
        Args:
            enable (bool): Enable or disable URC reports for NIDD messages.
        """
        res = self.send_command(f'AT+CRTDCP={int(enable)}')
        return res.ok

    # @abstractmethod
    def send_message_nidd(self, payload: bytes, **kwargs) -> MoMessage|None:
        """Send a message using Non-IP Data Delivery.
        
        Keyword arguments allows for device-specific parameters.
        
        Args:
            message (bytes): The message content/payload.
            **cid (int): The (PDP/PDN) context ID to use (default: 1).
            **rai (int): Release Assistance Indicator none (0),
                done on tx (1), done on rx (2)
            **data_type (int): Regular (0) or Exception (1)
        
        Returns:
            MoMessage object with optional metadata, or None if it could not
                be sent.
        """
        cid = kwargs.get('cid', 1)
        res = self.send_command('AT+CSODCP?')
        if not res.ok:
            raise NotImplementedError('Requires module-specific subclass')
        _log.debug('Sending NIDD message without confirmation')
        cmd = f'AT+CSODCP={cid},{len(payload)},"{payload.hex()}"'
        rai = kwargs.get('rai')
        data_type = kwargs.get('data_type')
        if rai is not None:
            cmd += f',{rai}'
        if data_type is not None:
            if rai is None:
                cmd += ','
            cmd += f',{data_type}'
        res = self.send_command(cmd)
        if res.ok:
            return MoMessage(payload, PdnType.NON_IP)
        return None
    
    # @abstractmethod
    def receive_message_nidd(self, urc: str = '', **kwargs) -> MtMessage|bytes|None:
        """Parses a NIDD URC string to derive the MT/downlink bytes sent.
        
        Args:
            urc (str): The 3GPP standard +CRTDCP unsolicited output
            **raw (bool): If True returns `bytes`
        
        Returns:
            The payload `bytes` or `MtMessage` metadata with `payload`
        """
        res = self.send_command('AT+CRTDCP?')
        if not res.ok:
            raise NotImplementedError('Requires module-specific subclass')
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
        if not isinstance(payload, bytes) or kwargs.get('raw') is True:
            return payload
        return MtMessage(payload, transport=PdnType.NON_IP)
    
    # @abstractmethod
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
    
    # @abstractmethod
    def enable_udp_urc(self, enable: bool = True, **kwargs) -> bool:
        """Enables URC supporting UDP operation."""
        raise NotImplementedError('Must implement in subclass')
    
    # @abstractmethod
    def udp_socket_open(self, **kwargs) -> bool:
        """Open a UDP socket.
        
        Args:
            **server (str): The server IP or URL
            **port (int): The destination port of the server
            **cid (int): The context/session ID (default 1)
            **src_port (int): Optional source port to use when sending
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    # @abstractmethod
    def udp_socket_status(self, cid: int = 1) -> SocketStatus:
        """Get the status of the specified socket/context ID."""
        raise NotImplementedError('Requires module-specific subclass')
    
    # @abstractmethod
    def udp_socket_close(self, cid: int = 1) -> bool:
        """Close the specified socket."""
        raise NotImplementedError('Requires module-specific subclass')
    
    # @abstractmethod
    def send_message_udp(self, payload: bytes, **kwargs) -> MoMessage|None:
        """Send a message using UDP transport.

        Opens a socket if one does not exist. Socket is left open by default
        but may be auto-closed using `close_socket` flag in kwargs.
        
        Args:
            message (bytes): The binary blob to be sent
            **server (str): The server IP or URL if establishing a new socket
            **port (int): The server port if establishing a new socket
            **src_port (int): Optional source port to use
            **cid (int): The context/session ID (default 1)
            **await_urc (bool): If set and supported, wait for confirmation of
                send/fail before returning.
            **close_socket (bool): If set, closes the socket if it was opened
                by this operation.
        
        Returns:
            A `MoMessage` structure with `payload` and IP header metadata
        """
        raise NotImplementedError('Requires module-specific subclass')
    
    # @abstractmethod
    def receive_message_udp(self, urc: str = '', **kwargs) -> MtMessage|bytes|None:
        """Get MT/downlink data received over UDP.
        
        Args:
            **cid (int): Context/session ID (default 1)
            **urc (str): URC output including hex payload
            **size (int): Maximum bytes to read (default 256)
            **raw (bool): If True returns `bytes` otherwise returns `MtMessage`
        
        Returns:
            `MtMessage` structure with `payload` and IP address/port, 
                or `bytes` or `None` if no data was received
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
    
    # @abstractmethod
    def report_debug(self,
                     add_commands: Optional[list[str]] = None,
                     replace: Optional[list[str]] = None) -> None:
        """Log a set of module-relevant config settings and KPIs.
        
        Args:
            add_commands: A list of additional AT commands to send.
            replace: A list of default 3GPP commands to remove. `<all>` keyword
                can be used to replace all default debug commands.
        """
        if isinstance(add_commands, list):
            if not all(isinstance(cmd, str) for cmd in add_commands):
                raise ValueError('Invalid command(s) must be list of strings')
        else:
            add_commands = []
        if isinstance(replace, list):
            if not all(isinstance(cmd, str) for cmd in replace):
                raise ValueError('Invalid command(s) must be list of strings')
        else:
            replace = []
        debug_commands = self._debug_commands
        if '<all>' in replace:
            debug_commands = []
            replace = []
        for cmd in replace:
            if cmd in debug_commands:
                debug_commands.remove(cmd)
        debug_commands += add_commands
        for cmd in debug_commands:
            res = self.send_command(cmd, timeout=15)
            if res.ok:
                _log.info('%s => %s', cmd, dprint(res.info or 'OK'))
            else:
                _log.error('Failed to query %s (ErrorCode: %d)', cmd, res.result)
