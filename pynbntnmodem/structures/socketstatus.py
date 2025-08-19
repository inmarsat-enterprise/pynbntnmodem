"""Data class helper for UDP socket status for NB-NTN."""

from dataclasses import dataclass


@dataclass
class SocketStatus:
    """Metadata for a UDP socket including state and IP address.
    
    Attributes:
        active (bool): Indicator whether the socket is active.
        dst_ip (str): The destination server/IP address.
        dst_port (int): The destination port.
        src_ip (str): The source IP address (assigned by the network).
        src_port (int): The source port used.
    """
    active: bool = False
    dst_ip: str = ''
    dst_port: int = 0
    src_ip: str = ''
    src_port: int = 0
