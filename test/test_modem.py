import logging
import random
import time
import threading
from typing import Optional, Union, Callable
from unittest.mock import create_autospec

import pytest
from pyatcommand import AtErrorCode, AtResponse

from pynbntnmodem import (
    ModuleModel,
    NbntnModem,
    RegInfo,
    SigInfo,
    RadioAccessTechnology,
)
from pynbntnmodem.ntninit import default_init

logger = logging.getLogger()


@pytest.fixture
def modem():
    modem = NbntnModem()
    try:
        modem.connect()
    except (ConnectionError,):
        pass
    if modem.is_connected():
        modem._ntn_initialized = modem.get_rat() == RadioAccessTechnology.NBNTN
    else:
        modem = None
    yield modem
    if modem is not None:
        modem.disconnect()


ResponseType = Union[AtResponse, Callable[[str, dict], AtResponse]]
def res_ok(info: Optional[str] = None, ok: bool = True):
    return AtResponse(AtErrorCode.OK if ok else AtErrorCode.ERROR, info)


@pytest.fixture
def mock_modem():
    """Satellite Modem instance with send_command mocked."""
    
    def _make(response_map: dict[str, ResponseType],
              background_commands: Optional[list[str]] = None,
              delay_map: Optional[dict[str, float]] = None,
              urc_map: Optional[dict[str, tuple[str, float]]] = None):
        # Configure defaults
        background_commands = background_commands or ['AT', 'ATE1', 'ATV1']
        delay_map = delay_map or {}
        urc_map = urc_map or {}
        
        modem = NbntnModem(apn='viasat.poc')
        modem._is_initialized = True
        # Replace command keyword substitutions
        replace_keys = []
        for cmd in response_map:
            if any(swap in cmd for swap in ['<pdn_type>', '<apn>']):
                pdn_type = modem.pdp_type.name.replace('_', '-')
                newcmd = cmd.replace('<pdn_type>', pdn_type)
                newcmd = newcmd.replace('<apn>', modem.apn)
                replace_keys.append({'old': cmd, 'new': newcmd})
        for r in replace_keys:
            for map in [response_map, delay_map, urc_map]:
                if r['old'] in map:
                    map[r['new']] = map[r['old']]
                    del map[r['old']]

        def emit_urc(urc: str, delay: float):
            def _worker():
                time.sleep(delay)
                modem.inject_urc(urc)
            threading.Thread(target=_worker, daemon=True).start()
        
        def send_side_effect(cmd, **kwargs):
            if cmd in delay_map:
                time.sleep(delay_map[cmd])
            if cmd in response_map:
                resp = response_map[cmd]
                if callable(resp):
                    return resp(cmd, kwargs)
                if cmd in urc_map:
                    urc, delay = urc_map[cmd]
                    emit_urc(urc, delay)
                return response_map[cmd]
            if cmd in background_commands:
                return AtResponse(AtErrorCode.OK)
            return AtResponse(AtErrorCode.ERROR)
        
        mocked_send = create_autospec(modem.send_command,
                                      side_effect=send_side_effect)
        modem.send_command = mocked_send
        return modem
    
    return _make


def test_get_model(mock_modem, modem: NbntnModem|None):  # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem({
            'ATI': res_ok('Manufacturer: Murata Manufacturing Co., Ltd\n'
                        'Model: LBAD0XX1SC-DM\n'
                        'Revision: RK_03_02_00_00_45021_001'),
        })
    model = modem.get_model()
    assert isinstance(model, ModuleModel)
    logger.info('Found model: %s', model.name)

    
def test_get_firmware_version(mock_modem, modem: NbntnModem|None):   # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem({
            'AT+CGMR': res_ok('RK_03_02_00_00_45021_001'),
        })
    fwv = modem.firmware_version
    assert fwv != ''
    logger.info('Found firmware version: %s', fwv)


def test_get_imei(mock_modem, modem: NbntnModem|None):   # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem({
            'AT+CGSN': res_ok('351521108462706'),
        })
    imei = modem.imei
    assert len(imei) >= 15
    logger.info('Found IMEI: %s', imei)


def test_get_imsi(mock_modem, modem: NbntnModem|None):   # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem({
            'AT+CIMI': res_ok('999999999999999'),
        })
    imsi = modem.imsi
    assert len(imsi) == 15
    logger.info('Found IMSI: %s', imsi)


def test_get_apn(mock_modem, modem: NbntnModem|None):    # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem({
            'AT+CGDCONT?': res_ok('1,"IP","data.mono",,0,0,0,0,0,,0,,,,'),
        })
    apn = modem.apn
    assert len(apn) > 0
    logger.info('Found APN: %s', apn)


def test_ntn_intialize(mock_modem, modem: NbntnModem|None):  # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem(
            response_map = {i.cmd: AtResponse(i.res)
                            for i in default_init if i.cmd is not None},
            delay_map = {i.cmd: random.uniform(1, i.timeout / 2)
                         for i in default_init if i.timeout},
            urc_map = {i.cmd: (f'\r\n{i.urc.urc}\r\n', 2)
                       for i in default_init if i.urc is not None},
        )
        modem._ntn_initialized = False
    assert modem.initialize_ntn()


def test_get_reginfo(mock_modem, modem: NbntnModem|None):    # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem({
            'AT+CEREG?': res_ok('+CEREG: 0,0'),
        })
    reg_info = modem.get_reginfo()
    assert isinstance(reg_info, RegInfo)
    logger.info('Found registration info: %s', reg_info)


def test_get_siginfo(mock_modem, modem: NbntnModem|None):    # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem({
            'AT+CESQ': res_ok('99,99,255,255,255,255'),
        })
    sig_info = modem.get_siginfo()
    assert isinstance(sig_info, SigInfo)
    logger.info('Found registration info: %s', sig_info)


def test_urc_trigger(mock_modem, modem: NbntnModem|None):    # type: ignore
    urc_delay = 2
    if modem is None:
        modem: NbntnModem = mock_modem(
            response_map = { 'ATZ': res_ok() },
            urc_map = { 'ATZ': ('\r\nRDY\r\n', urc_delay) },
        )
    assert modem.send_command('ATZ').ok
    time.sleep(urc_delay + 0.25)
    urc = modem.get_urc()
    assert urc == 'RDY'


def test_report_debug(mock_modem, modem: NbntnModem|None, caplog):     # type: ignore
    if modem is None:
        modem: NbntnModem = mock_modem(
            response_map = {
                'AT+CMEE?': res_ok('+CMEE: 2'),   # Enhanced error output
                'ATI': res_ok('Manufacturer: ACME'),   # module information
                'AT+CGMR': res_ok('1.2.3'),   # firmware/revision
                'AT+CIMI': res_ok('+CME ERROR: SIM not inserted'),   # IMSI
                'AT+CGSN': res_ok('123456789012345'),   # IMEI
                'AT+CFUN?': res_ok('+CFUN: 1'),   # Module radio function configured
                'AT+CEREG?': res_ok('0,0'),   # Registration status and URC config
                'AT+CGDCONT?': res_ok('+CGDCONT: 1,"IP","viasat.ip",,0,0,0,0,0,,0,,,,'
                                      '\n+CGDCONT: 2,"Non-IP","viasat.poc",,0,0,0,0,0,,0,,,,'),   # PDP/PDN Context configuration
                'AT+CGPADDR': res_ok('+CGPADDR: 1'
                                     '\n+CGPADDR: 2'),   # IP address(es) assigned by network
                'AT+CPSMS?': res_ok('+CPSMS: 0,,,"00101100","00001010"'),   # Power saving mode settings (requested)
                'AT+CEDRXS?': res_ok(),   # eDRX settings (requested)
                'AT+CEDRXRDP': res_ok('+CEDRXRDP: 0'),   # eDRX dynamic parameters
                'AT+CRTDCP?': res_ok('+CRTDCP: 0'),   # Reporting of terminating data via control plane
                'AT+CSCON?': res_ok('+CSCON: 0,0'),   # Signalling connection status
                'AT+CESQ': res_ok('+CESQ: 99,99,255,255,255,255'),   # Signal quality including RSRQ indexed from 0 = -19.5 in 0.5dB increments, RSRP indexed from 0 = -140 in 1 dBm increments
            },
        )
    caplog.set_level('DEBUG')
    modem.report_debug()
    success_str = ' => '
    fail_str = 'Failed to query'
    successes = []
    failures = []
    for record in caplog.records:
        if success_str in record.message:
            successes.append(record.message.split(success_str)[0])
        elif fail_str in record.message:
            failures.append(record.message.split(fail_str)[1])
    remove_failures = [
        '+CGPADDR?',   # IP address may not be assigned yet
    ]
    failures = [f for f in failures if not any(r in f for r in remove_failures)]
    for failure in failures:
        logger.error(failure)
    assert len(failures) == 0
