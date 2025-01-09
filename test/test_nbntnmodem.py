import logging
import os

import pytest

from pyatcommand import AtErrorCode, AtTimeout
from pynbntnmodem import (NbntnBaseModem, NbntnModem, clone_and_load_modem_classes)

test_log = logging.getLogger(__name__)


def test_basic(caplog):
    """"""
    caplog.set_level('INFO')
    modem = NbntnModem()
    modem.connect()
    assert modem.is_connected()
    modem.report_debug()
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
    for cmd in debug_commands:
        assert f'{cmd} =>' in caplog.text or f'Failed to query {cmd}' in caplog.text
    modem.disconnect()


# TODO: parameterize with ATQ as timeout vs nonsense command as error
def test_initialize_ntn_with_retry(caplog):
    """"""
    # caplog.set_level('INFO')
    max_retries = 2
    test_init = [
        {
            'cmd': 'ATQ1',
            'res': AtErrorCode.OK,
            'timeout': 1,
            'why': 'disable responses to simulate timeouts'
        },
        {
            'cmd': 'AT',
            'res': AtErrorCode.OK,
            'timeout': 1,
            'retry': { 'count': max_retries },
            'why': 'try get response in quiet mode'
        },
    ]
    modem = NbntnModem()
    modem.connect()
    assert modem.is_connected()
    assert modem.initialize_ntn(ntn_init=test_init) is False
    substring = 'Failed attempt'
    retry_count = sum(substring in record.message for record in caplog.records)
    assert retry_count == max_retries
    with pytest.raises(AtTimeout):
        modem.send_command('ATQ0')
    assert modem.send_command('AT') == AtErrorCode.OK


def test_repo_import():
    token = os.getenv('GITHUB_TOKEN')
    if token:
        token += '@'
    repo_names = os.getenv('REPO_NAMES', '').split(',')
    repo_urls = [f'https://{token}github.com/inmarsat-enterprise/nbntn-{rn}.git'
                 for rn in repo_names]
    branch = os.getenv('REPO_BRANCH', 'main')

    try:
        modem_classes = clone_and_load_modem_classes(repo_urls, branch)
        test_log.info('Loaded modem classes: %s', list(modem_classes.keys()))

        # Instantiate and use a modem class (example)
        for name, ModemClass in modem_classes.items():
            assert name.replace('_', '-') in repo_names
            assert issubclass(ModemClass(), NbntnBaseModem)
    except Exception as e:
        test_log.error(f"Error: {e}")
        assert e is None
