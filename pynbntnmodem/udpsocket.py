"""Provide a socket-style interface for UDP via NB-NTN.

"""

import atexit
import logging
import socket
import threading
import time
from typing import Callable, Any

from .constants import NBNTN_MAX_MSG_SIZE
from .modem import MoMessage, MtMessage

__all__ = ['UdpSocketBridge']

_log = logging.getLogger(__name__)


class UdpSocketBridge:
    """Provides a raw socket-like interface on the local host.
    
    Acts as bridge between a raw socket and the modem's AT commands.
    """
    def __init__(self,
                 server: str,
                 port: int,
                 open: Callable[[Any], bool],
                 send: Callable[[bytes], MoMessage|None],
                 recv: Callable[[Any], bytes|MtMessage|None],
                 close: Callable[[], bool],
                 event_trigger: bool = False):
        """Create a raw socket.
        
        Args:
            server (str): The IP address or server name to connect to.
            port (int): The UDP port to use.
            open (Callable[[str, int], bool]): The callback function to open
                a UDP socket. Takes `server`, `port` and returns success.
            send (Callable[[bytes], MoMessage|None]): The callback function
                to send UDP data on the modem socket.
            recv (Callable[[Any], bytes|MtMessageNone]): The callback function
                to receive UDP data from the modem socket.
            close (Callable[[], bool]): The callback function to close
                the modem socket.
        """
        if not isinstance(server, str) or not server:
            raise ValueError('Invalid server')
        self._server = server
        if not isinstance(port, int) or port not in range(0, 65536):
            raise ValueError('Invalid port')
        self._port = port
        self._cb_open = open
        self._cb_send = send
        self._cb_recv = recv
        self._cb_close = close
        self._on_exit = atexit.register(self.close)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(('127.0.0.1', self._port))
        self._sock.setblocking(False)
        self._running: bool = True
        self._thread = threading.Thread(target=self._run,
                                        name='udp_socket_bridge',
                                        daemon=True)
        self._thread.start()
        self._event_trigger = event_trigger
        self._recv_event = threading.Event()
        self._recv_event.clear()
    
    def _run(self):
        opened = self._cb_open(server=self._server, port=self._port)
        if not opened:
            raise IOError(f'Failed to open UDP socket {self._server}:{self._port}')
        _log.debug('UDP socket bridge running on port %d', self._port)
        while self._running:
            # check for incoming data
            if not self._event_trigger or self._recv_event.is_set():
                self._recv_event.clear()
                downlink = self._cb_recv(size=NBNTN_MAX_MSG_SIZE)
                if isinstance(downlink, bytes) and len(downlink) > 0:
                    rcvd = self._sock.sendto(downlink, ('127.0.0.1', self._port))
                    _log.debug('Received %d bytes OTA', rcvd)
            # forward local data
            try:
                send_data, _ = self._sock.recvfrom(1024)
                if isinstance(send_data, bytes) and len(send_data) > 0:
                    if len(send_data) <= (NBNTN_MAX_MSG_SIZE - 20 - 8):
                        uplink = self._cb_send(send_data)
                        if isinstance(uplink, MoMessage):
                            _log.debug('Sent %d bytes OTA', uplink.size)
                    else:
                        _log.warning('Data too large to send')
            except (socket.timeout, BlockingIOError):
                pass
            time.sleep(1)   # avoid excessive processing
    
    def receive_event(self):
        """Trigger a received data event."""
        self._recv_event.set()
    
    def close(self):
        """Terminate the socket bridge."""
        self._running = False
        closed = self._cb_close()
        if not closed:
            _log.error('Failed to close UDP socket')
        self._thread.join()
