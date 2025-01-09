"""Provide a socket-style interface for UDP via NB-NTN"""

import queue

from typing import Callable

class UdpSocket:
    """Provides a socket-like interface for other Python libraries like aiocoap.
    
    Expects the parent to instantiate the UdpSocket and put UDP data from URCs
    into the socket recv_queue.
    """
    def __init__(self,
                 socket_open: Callable,
                 socket_send: Callable,
                 socket_close: Callable,):
        self.socket_open = socket_open
        self.socket_send = socket_send
        self.socket_close = socket_close
        self.recv_queue = queue.Queue()
        self.recv_timeout = 5
        self.running = True
    
    def connect(self, ip: str, port: int):
        """"""
        self.socket_open(ip, port)
    
    def send(self, data: bytes):
        """"""
        self.socket_send(data)
    
    def recv(self, buffer_size=1024):
        """"""
        try:
            while self.running:
                data = self.recv_queue.get(timeout=self.recv_timeout)
                return data[:buffer_size]
        except queue.Empty:
            raise TimeoutError('Timeout waiting for UDP data')
    
    def close(self):
        """"""
        self.running = False
        self.socket_close()
