"""Data class helper for PDP/PDN Context.

The Packet Data Protocol or Packet Data Network Context is the logical
connection between a mobile device and a mobile network that allows exchange of
packets.
"""
from dataclasses import dataclass

from pynbntnmodem.constants import PdpType


@dataclass
class PdpContext:
    """Attributes of a NB-NTN Packet Data Protocol context/definition."""
    id: int = 1   # context ID
    pdp_type: PdpType = PdpType.IP
    apn: str = ''
    ip: 'str|None' = ''   # the IP address if type is IP and attached
