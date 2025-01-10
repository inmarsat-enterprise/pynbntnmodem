import logging
import os

import pytest
from pyatcommand import AtErrorCode, AtTimeout

from pynbntnmodem import (
    DefaultModem,
    NbntnBaseModem,
    ModuleManufacturer,
    ModuleModel,
    clone_and_load_modem_classes,
    get_model,
)

test_log = logging.getLogger(__name__)


@pytest.fixture
def generic_modem():
    return DefaultModem(apn=os.getenv('TEST_APN', 'viasat.poc'))


@pytest.mark.skip
def test_detect(generic_modem: DefaultModem):
    modem = generic_modem
    modem.connect()
    model = get_model(modem._serial)
    assert model.name == DefaultModem.model_name()


def test_init(generic_modem: DefaultModem):
    modem = generic_modem
    modem.connect()
    assert modem.initialize_ntn() is True


def test_debug(generic_modem: DefaultModem, caplog):
    caplog.set_level('DEBUG')
    modem = generic_modem
    modem.connect()
    modem.report_debug()
    success_str = ' => '
    fail_str = 'Failed to query'
    successes = []
    failures = []
    for record in caplog.records:
        if success_str in record.message:
            successes.append(record.message.split(success_str)[0])
        elif fail_str in record.message:
            failures.append(record.message.split(fail_str)[1])
    remove_failures = [
        '+CGPADDR?',   # IP address may not be assigned yet
    ]
    failures = [f for f in failures if not any(r in f for r in remove_failures)]
    for failure in failures:
        test_log.error(failure)
    assert len(failures) == 0


# TODO: parameterize with ATQ as timeout vs nonsense command as error
def test_initialize_ntn_with_retry(caplog):
    """"""
    # caplog.set_level('INFO')
    max_retries = 2
    test_init = [
        {
            'cmd': 'ATQ1',
            'res': AtErrorCode.OK,
            'timeout': 1,
            'why': 'disable responses to simulate timeouts'
        },
        {
            'cmd': 'AT',
            'res': AtErrorCode.OK,
            'timeout': 1,
            'retry': { 'count': max_retries },
            'why': 'try get response in quiet mode'
        },
    ]
    modem = DefaultModem()
    modem.connect()
    assert modem.is_connected()
    assert modem.initialize_ntn(ntn_init=test_init) is False
    substring = 'Failed attempt'
    retry_count = sum(substring in record.message for record in caplog.records)
    assert retry_count == max_retries
    with pytest.raises(AtTimeout):
        modem.send_command('ATQ0')
    assert modem.send_command('AT') == AtErrorCode.OK


def test_repo_import():
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
    download_path = os.path.join(os.getcwd(), 'test')
    try:
        modem_classes = clone_and_load_modem_classes(repo_urls, branch, download_path)
        test_log.info('Loaded modem classes: %s', list(modem_classes.keys()))
        # Instantiate and use a modem class (example)
        for name, ModemClass in modem_classes.items():
            assert any(name.upper().startswith(mfr)
                       for mfr in ModuleManufacturer.__members__.keys())
            assert any(name.upper().endswith(mdl)
                       for mdl in ModuleModel.__members__.keys())
            assert issubclass(ModemClass, NbntnBaseModem)
            if download_path:
                filename = os.path.join(download_path, f'{name}.py')
                assert os.path.isfile(filename)
                os.remove(filename)
    except Exception as e:
        test_log.error(f"Error: {e}")
        assert e is None
