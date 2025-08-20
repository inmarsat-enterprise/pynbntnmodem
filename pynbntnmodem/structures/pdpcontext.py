"""Data class helper for PDP/PDN Context.

The Packet Data Protocol or Packet Data Network Context is the logical
connection between a mobile device and a mobile network that allows exchange of
packets.
"""
from dataclasses import dataclass
from typing import Optional

from pynbntnmodem.constants import PdnType


@dataclass
class PdnContext:
    """Attributes of a NB-NTN Packet Data Protocol context/definition."""
    id: int = 1   # context ID
    pdn_type: PdnType = PdnType.IP
    apn: str = ''
    ip: Optional[str] = None   # the IP address if type is IP and attached
    active: bool = False
