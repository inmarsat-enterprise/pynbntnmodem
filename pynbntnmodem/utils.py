import ipaddress
import logging
import re

from pyatcommand import AtClient, AtResponse

from pynbntnmodem import ModuleModel


_log = logging.getLogger(__name__)


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


def get_model(serial: AtClient) -> ModuleModel:
    """Queries a modem to determine its make/model"""
    res: AtResponse = serial.send_command('ATI', timeout=3)
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
        elif 'telit' in res.info.lower():
            if 'ME910G1' in res.info:
                return ModuleModel.ME910G1
        _log.warning('Unsupported model: %s', res)
        return ModuleModel.UNKNOWN
    raise OSError('Unable to get modem information')
