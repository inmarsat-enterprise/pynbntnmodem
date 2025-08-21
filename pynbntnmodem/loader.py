"""Utilities for loading NbntnModem subclasses.
"""

import logging
import importlib.util
import inspect
import os
import tempfile
import shutil
import subprocess
from typing import Type
from pathlib import Path

from . import modems
from .modem import NbntnModem
from .constants import ModuleModel

_log = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_ORG = 'inmarsat-enterprise'
GITHUB_REPOS = [
    'murata-type1sc',
    'quectel-cc660d',
]


# cache: {Path: loaded_module}
_module_cache: dict[Path, object] = {}


def load_module_from_path(module_path: Path):
    """Load a Python module directly from a file path.
    
    Avoid touching sys.path.
    """
    if module_path in _module_cache:
        return _module_cache[module_path]
    module_name = module_path.stem
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load module from {module_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_cache[module_path] = module
    return module


def clone_and_load_modem_classes(repo_urls: list[str],
                                 branch: str = 'main',
                                 download_path: str = '',
                                 ) -> dict[str, Type[NbntnModem]]:
    """Clone multiple Git repositories and load subclasses of SatelliteModem.

    Args:
        repo_urls (list[str]): A list of Git repository URLs.
        branch (str): The branch to clone. Defaults to 'main'.

    Returns:
         A dictionary of modem class names and their corresponding classes.
    """
    modem_classes: dict[str, Type[NbntnModem]] = {}
    # Create a temporary directory to clone repositories
    with tempfile.TemporaryDirectory() as temp_dir:
        for repo_url in repo_urls:
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            repo_path = os.path.join(temp_dir, repo_name)
            _log.debug('Cloning git repository into %s...', repo_path)
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', '--branch',
                 branch, repo_url, repo_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                _log.error("Failed to clone repository %s: %s",
                           repo_url, result.stderr)
                continue
            _log.debug("Git repository %s cloned successfully.", repo_name)
            # Find Python files in the repository and load modem classes
            for root, _, files in os.walk(repo_path):
                if any(p in Path(root).parts for p in ['tests', 'examples']):
                    continue
                for file in files:
                    if file in ['__init__.py', 'main.py']:
                        continue
                    if file.endswith('.py'):
                        file_path = Path(root) / file
                        try:
                            submodule = load_module_from_path(file_path)
                        except Exception as e:
                            _log.exception('Failed to load module %s: %s',
                                           file_path, e)
                            continue
                        for _, cls in inspect.getmembers(submodule, inspect.isclass):
                            if (issubclass(cls, NbntnModem) and
                                cls is not NbntnModem):
                                modem_classes[cls.__name__] = cls
                                _log.debug('Loaded modem class: %s', cls.__name__)
                        # Copy to download_path if requested
                        if download_path:
                            os.makedirs(download_path, exist_ok=True)
                            dest_path = Path(download_path) / file
                            shutil.copy(file_path, dest_path)
                            _log.debug('Copied %s to %s', file, dest_path)
    return modem_classes


def mutate_modem(modem: NbntnModem, **kwargs) -> NbntnModem:
    """Mutate and return the model-specific subclass of the satellite modem.
    
    Attempts to find the module in `modems_path` which defaults to the `modems`
    folder under `pynbntnmodem`.
    If not found, will attempt to clone/download from GitHub private repository
    if a GITHUB_TOKEN environment variable is present.
    
    Args:
        modem (NbntnModem): The base/unknown modem.
        **module (module): The module containing the subclass python files.
            Downloaded files from GitHub will be stored here.
        **mixin (NbntnModem): Optional mixin extension subclass to apply.
    
    Returns:
        Subclass of NbntnModem.
    
    Raises:
        ModuleNotFoundError if unable to load the subclass.
    """
    was_connected = modem.is_connected()
    if not was_connected:
        modem.connect()
    model = modem.get_model()
    if model == ModuleModel.UNKNOWN:
        raise ModuleNotFoundError('Unrecognized modem')
    if model == modem._model:
        return modem
    pymodule = kwargs.pop('module', modems)
    modems_path = Path(pymodule.__path__[0])
    file_tag = f'{model.name.lower()}.py'
    modem_path = next(
        (p for p in modems_path.glob('*.py') if p.name.endswith(file_tag)),
        None,
    )
    if modem_path is None:
        try:
            token = kwargs.get('github_token', GITHUB_TOKEN)
            if token:
                _log.debug('Attempting to clone model subclass from GitHub...')
                org = kwargs.get('github_org_name', GITHUB_ORG)
                repos: list[str] = kwargs.get('github_repos', GITHUB_REPOS)
                for repo_name in repos:
                    if repo_name.replace('-', '_').endswith(model.name.lower()):
                        _log.info('Copying %s from GitHub to %s',
                                    model.name, modems_path)
                        repo_url = (f'https://{token}@github.com'
                                    f'/{org}/pynbntnmodem-{repo_name}')
                        clone_and_load_modem_classes(
                            [repo_url], download_path=str(modems_path)
                        )
                # refresh after download
                modem_path = next(
                    (p for p in modems_path.glob('*.py') if p.name.endswith(file_tag)),
                    None,
                )
        except Exception as e:
            raise ModuleNotFoundError(f'No module for {model.name}') from e
    # Check if download still did not get the target file
    if modem_path is None:
        raise ModuleNotFoundError(f'No Python file found for {model.name}')
    submodule = load_module_from_path(modem_path)
    for _, candidate in inspect.getmembers(submodule, inspect.isclass):
        if issubclass(candidate, NbntnModem):
            if getattr(candidate, '_model', None) == model:
                # Disconnect for state prior to mutation
                if not was_connected:
                    modem.disconnect()
                mixin = kwargs.get('mixin')
                if mixin and issubclass(mixin, NbntnModem):
                    Extended = type(
                        f'Extended{candidate.__name__}',
                        (candidate, mixin),
                        {}
                    )
                    modem.__class__ = Extended
                else:
                    modem.__class__ = candidate
                modem._post_mutate()
                return modem
    # Fall-through
    raise ModuleNotFoundError(f'No subclass found for {model.name}')
