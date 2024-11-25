"""Abstraction partial example for a Sony/Altair based modem."""

import logging

from pyatcommand import AtClient, AtErrorCode

from pynbntnmodem import NbntnModem, Chipset

__all__ = [ 'AltairNbModem', 'MODEM_SUBCLASS' ]

_log = logging.getLogger(__name__)


ntn_init = [
    {
        'cmd': 'AT+CFUN=0',
        'res': AtErrorCode.OK,
        'timeout': 30,
        'retry': { 'count': 0 },
        'why': 'stop radio for configuration',
    },
    {
        'cmd': 'AT%SETACFG="radiom.config.multi_rat_enable","true"',
        'res': AtErrorCode.OK,
        'timeout': 5,
        'why': 'enable multi-RAT capability',
    },
    {
        'cmd': 'AT%SETACFG="radiom.config.preferred_rat_list","none"',
        'res': AtErrorCode.OK,
        'why': 'disable preferred RAT list',
    },
    {
        'cmd': 'AT%SETACFG="radiom.config.auto_preference_mode","none"',
        'res': AtErrorCode.OK,
        'why': 'disable automatic RAT switching',
    },
    {
        'cmd': 'ATZ',
        'res': AtErrorCode.OK,
        'urc': '%BOOTEV:0',
        'why': 'reset for configured parameter use',
    },
    {
        'cmd': 'AT%RATACT="NBNTN",1',
        'res': AtErrorCode.OK,
        'timeout': 10,
        'why': 'enable NBNTN RAT',
    },
    {
        'cmd': 'AT%SETACFG="modem_apps.Mode.AutoConnectMode","true"',
        'res': AtErrorCode.OK,
        'why': 'enable auto-connect mode',
    },
    {
        'cmd': 'AT+CGDCONT=1,"<pdn_type>","<apn>"',
        'res': AtErrorCode.OK,
        'timeout': 5,
        'why': 'configure APN and PDN type',
    },
    {
        'cmd': 'AT+CEREG=5',
        'res': AtErrorCode.OK,
        'why': 'enable detailed registration URCs including PSM',
    },
    {
        'cmd': 'AT+CFUN=1',
        'res': AtErrorCode.OK,
        'timeout': 30,
        'retry': { 'count': 1 },
        'why': 'enable radio',
    },
]

class AltairNbModem(NbntnModem):
    """Class representing Murata Type1-SC module.
    """
    _chipset = Chipset.ALT1250

    def __init__(self, serial: AtClient, **kwargs) -> None:
        super().__init__(serial, **kwargs)
    
    def initialize_ntn(self, **kwargs) -> bool:
        return super().initialize_ntn(ntn_init=ntn_init)


# Always include the below reference in the template
MODEM_SUBCLASS = AltairNbModem
