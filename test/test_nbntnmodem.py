# import pytest

from pynbntnmodem import NbntnModem


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
