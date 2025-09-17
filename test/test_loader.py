import os

import serial

from pynbntnmodem import NbntnModem, clone_and_load_modem_classes, mutate_modem


GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_ORG = 'inmarsat-enterprise'
REPOS = [
    'pynbntnmodem-murata-type1sc',
]


def test_clone_and_load():
    if not GITHUB_TOKEN:
        raise ValueError('Requires GitHub PAT for private repo access')
    repo_urls = [f'https://{GITHUB_TOKEN}@github.com/{GITHUB_ORG}/{x}'
                 for x in REPOS]
    modems = clone_and_load_modem_classes(repo_urls)
    assert len(modems.keys()) > 0
    for name, subcls in modems.items():
        assert issubclass(subcls, NbntnModem)
        assert name.replace('_', '') == subcls.__name__.lower()


def test_detect_modem():
    modem = NbntnModem()
    modem.connect()
    modem = mutate_modem(modem)
    assert isinstance(modem, NbntnModem)
    assert modem.model != 'UNKNOWN'
    assert modem.is_connected()
    assert modem.send_command('AT').ok
    assert isinstance(modem._serial, serial.Serial)
