import logging
import time
from typing import Optional
from unittest.mock import create_autospec

import pytest
from pyatcommand import AtErrorCode, AtResponse

from pynbntnmodem import (
    ModuleModel,
    NbntnModem,
    RegInfo,
    SigInfo,
)

logger = logging.getLogger()


@pytest.fixture
def modem():
    modem = NbntnModem()
    modem.connect()
    yield modem
    modem.disconnect()


@pytest.fixture
def mock_modem():
    """Satellite Modem instance with send_command mocked."""
    
    def _make(response_map: dict[str, AtResponse],
              background_commands: list[str] = ['AT', 'ATE1', 'ATV1'],
              delay_map: Optional[dict[str, float]] = None):
        
        if not delay_map:
            delay_map = {}

        def send_side_effect(cmd, **kwargs):
            if cmd in response_map:
                if cmd in delay_map:
                    time.sleep(delay_map[cmd])
                return response_map[cmd]
            if cmd in background_commands:
                return AtResponse(AtErrorCode.OK)
            return AtResponse(AtErrorCode.ERROR)
        
        modem = NbntnModem()
        modem._is_initialized = True
        mocked_send = create_autospec(modem.send_command)
        mocked_send.side_effect = send_side_effect
        modem.send_command = mocked_send
        return modem
    
    return _make


def test_get_model(mock_modem):
    modem: NbntnModem = mock_modem({
        'ATI': AtResponse(AtErrorCode.OK,
                          info='Manufacturer: Murata Manufacturing Co., Ltd\n'
                          'Model: LBAD0XX1SC-DM\n'
                          'Revision: RK_03_02_00_00_45021_001'),
    })
    model = modem.get_model()
    assert isinstance(model, ModuleModel)
    logger.info('Found model: %s', model.name)

    
def test_get_firmware_version(mock_modem):
    modem: NbntnModem = mock_modem({
        'AT+CGMR': AtResponse(AtErrorCode.OK, info='RK_03_02_00_00_45021_001'),
    })
    fwv = modem.firmware_version
    assert fwv != ''
    logger.info('Found firmware version: %s', fwv)


def test_get_imei(mock_modem):
    modem: NbntnModem = mock_modem({
        'AT+CGSN': AtResponse(AtErrorCode.OK, info='351521108462706'),
    })
    imei = modem.imei
    assert len(imei) >= 15
    logger.info('Found IMEI: %s', imei)


def test_get_imsi(mock_modem):
    modem: NbntnModem = mock_modem({
        'AT+CIMI': AtResponse(AtErrorCode.OK, info='901980020000001'),
    })
    imsi = modem.imsi
    assert len(imsi) == 15
    logger.info('Found IMSI: %s', imsi)


def test_get_apn(mock_modem):
    modem: NbntnModem = mock_modem({
        'AT+CGDCONT?': AtResponse(AtErrorCode.OK, info='1,"IP","data.mono",,0,0,0,0,0,,0,,,,'),
    })
    apn = modem.apn
    assert len(apn) > 0
    logger.info('Found APN: %s', apn)


def test_ntn_intialize(mock_modem):
    modem: NbntnModem = mock_modem(
        response_map = {
            'AT+CFUN=0': AtResponse(AtErrorCode.OK),
            'AT+CEREG=5': AtResponse(AtErrorCode.OK),
            'AT+CGDCONT=1,"NON-IP",""': AtResponse(AtErrorCode.OK),
            'AT+CFUN=1': AtResponse(AtErrorCode.OK),
        },
        delay_map = { 'AT+CFUN=1': 3 },
    )
    assert modem.initialize_ntn()


def test_get_reginfo(mock_modem):
    modem: NbntnModem = mock_modem({
        'AT+CEREG?': AtResponse(AtErrorCode.OK, info='+CEREG: 0,0'),
    })
    reg_info = modem.get_reginfo()
    assert isinstance(reg_info, RegInfo)
    logger.info('Found registration info: %s', reg_info)


def test_get_siginfo(mock_modem):
    modem: NbntnModem = mock_modem({
        'AT+CESQ': AtResponse(AtErrorCode.OK, info='99,99,255,255,255,255'),
    })
    sig_info = modem.get_siginfo()
    assert isinstance(sig_info, SigInfo)
    logger.info('Found registration info: %s', sig_info)
