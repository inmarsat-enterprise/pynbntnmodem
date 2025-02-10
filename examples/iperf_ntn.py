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
    DefaultModem,
    PdpType,
    UrcType,
    UdpSocketBridge,
    clone_and_load_modem_classes,
    get_model,
)

logger = logging.getLogger(__name__)
file_ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s,%(levelname)s,%(message)s',
                    datefmt='%Y-%m-%dT%H:%M:%S',
                    filename=f'./logs/iperf-{file_ts}.log')


def get_modem_classes():
    token = os.getenv('GITHUB_TOKEN')
    if token:
        token += '@'
    repo_names = os.getenv('REPO_NAMES', '').split(',')
    for i, repo_name in enumerate(repo_names):
        if not repo_name.startswith('nbntn-'):
            repo_names[i] = f'nbntn-{repo_name}'
        if repo_name.endswith('.git'):
            repo_names[i] = repo_names[i][:-4]
    repo_urls = [f'https://{token}github.com/inmarsat-enterprise/{rn}.git'
                 for rn in repo_names]
    branch = os.getenv('REPO_BRANCH', 'main')
    download_path = os.path.join(os.getcwd(), 'test/tmp')
    modem_classes = clone_and_load_modem_classes(repo_urls, branch, download_path)
    return modem_classes


def run_iperf_bridge():
    modem = DefaultModem()
    modem.connect(port=os.getenv('SERIAL_PORT'))
    modem_classes = get_modem_classes()
    model = get_model(modem._serial)
    for cls in modem_classes.values():
        if cls._model == model:
            modem = cls(client=modem._serial)
            break
    modem.pdp_type = PdpType.IP
    modem.apn = 'viasat.ip'
    modem.udp_server = os.getenv('UDP_SERVER')
    modem.udp_server_port = 5001
    reg_info = modem.get_reginfo()
    if not reg_info.is_registered() or not modem.ip_address:
        if not modem.initialize_ntn():
            raise ValueError('Unable to initialize modem')
    while not reg_info.is_registered():
        reg_info = modem.get_reginfo()
        if reg_info.is_registered():
            break
        time.sleep(1)
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
