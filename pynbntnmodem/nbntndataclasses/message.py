"""Data class helper for Messages.

Provides an abstraction allowing for distinction of payload from IP overhead,
and determination of packet size.
"""

import ipaddress
from dataclasses import dataclass
from typing import Optional, Union

from pynbntnmodem.constants import PdpType

__all__ = [ 'BaseMessage', 'MoMessage', 'MtMessage' ]

@dataclass
class BaseMessage:
    payload: bytes
    transport: PdpType
    id: Optional[Union[int, str]] = None
    
    @property
    def size(self) -> int:
        if self.transport is None or self.payload is None:
            return 0
        if self.transport == PdpType.NON_IP:
            return len(self.payload)
        if self.transport == PdpType.IP:
            return len(self.payload) + 20 + 8
        if self.transport == PdpType.IPV6:
            return len(self.payload) + 40 + 8
        ip = None
        if hasattr(self, 'dst_ip'):
            ip = getattr(self, 'dst_ip')
        elif hasattr(self, 'src_ip'):
            ip = getattr(self, 'src_ip')
        if not ip:
            return 0
        try:
            parsed_ip = ipaddress.ip_address(ip)
            if isinstance(parsed_ip, ipaddress.IPv4Address):
                return len(self.payload) + 20 + 8
            return len(self.payload) + 40 + 8
        except ValueError:
            return 0


@dataclass
class MoMessage(BaseMessage):
    """Metadata for Mobile-Terminated message including payload and source"""
    dst_ip: Optional[str] = None
    dst_port: Optional[int] = None
    

@dataclass
class MtMessage(BaseMessage):
    """Metadata for Mobile-Terminated message including payload and source"""
    src_ip: Optional[str] = None
    dst_port: Optional[int] = None
