"""Example using iperf testing over UDP.

Example use with iperf:

* Server-side: iperf -u -s -D -p 5001
* Client-side: iperf -c 127.0.0.1 -u -l 228 -t 60 -b 100b -p 5001

"""

import os
import logging
import time
from datetime import datetime, timezone

from pynbntnmodem import (
    NbntnModem,
    PdnType,
    UrcType,
    UdpSocketBridge,
    mutate_modem,
)

logger = logging.getLogger(__name__)
file_ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s,%(levelname)s,%(message)s',
                    datefmt='%Y-%m-%dT%H:%M:%S',
                    filename=f'./logs/iperf-{file_ts}.log')


def run_iperf_bridge():
    modem = NbntnModem(
        apn='viasat.ip',
        pdp_type=PdnType.IP,
        udp_server=os.getenv('UDP_SERVER', ''),
        udp_server_port=int(os.getenv('UDP_SERVER_PORT', '5001')),
    )
    modem.connect()
    try:
        modem = mutate_modem(modem)
    except ModuleNotFoundError:
        logger.warning('Unable to find model-specific subclass for %s %s',
                       modem.manufacturer, modem.get_model().name)
    if not modem.initialize_ntn():
        raise IOError('Unable to initialize NTN configuration of modem')
    while not modem.get_reginfo().is_registered():
        logger.info('Waiting for modem to register...')
        time.sleep(3)
    socket_bridge = UdpSocketBridge(server=modem.udp_server,
                                    port=modem.udp_server_port,
                                    open=modem.udp_socket_open,
                                    send=modem.send_message_udp,
                                    recv=modem.receive_message_udp,
                                    close=modem.udp_socket_close,
                                    event_trigger=True)
    while True:
        if modem.check_urc():
            urc = modem.get_response()
            logger.debug('Received URC: %s', urc)
            urc_type = modem.get_urc_type(urc)
            if urc_type == UrcType.UDP_MT_RCVD:
                socket_bridge.receive_event()


if __name__ == '__main__':
    run_iperf_bridge()
