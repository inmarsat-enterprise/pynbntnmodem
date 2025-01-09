"""Data class helper for UDP socket status for NB-NTN."""

from dataclasses import dataclass


@dataclass
class SocketStatus:
    """Metadata for a UDP socket including state and IP address.
    
    Attributes:
        active (bool): Indicator whether the socket is active.
        ip_address (str): The IP address assigned by the network.
    """
    active: bool = False
    ip_address: str = ''
