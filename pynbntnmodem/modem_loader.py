"""This is a placeholder"""
import importlib.util
import logging
import os
import tempfile
import shutil
import subprocess
from typing import Type

from pynbntnmodem.modem import NbntnBaseModem

__all__ = ['clone_and_load_modem_classes', 'load_modem_class']

_log = logging.getLogger(__name__)


def clone_and_load_modem_classes(repo_urls: 'list[str]',
                                 branch: str = 'main',
                                 download_path: str = '',
                                 ) -> dict[str, Type[NbntnBaseModem]]:
    """
    Clone multiple Git repositories and load subclasses of NbntnModem.

    Args:
        repo_urls (list[str]): A list of Git repository URLs.
        branch (str): The branch to clone. Defaults to 'main'.

    Returns:
        dict[str, Type[NbntnModem]]: A dictionary of modem class names and their corresponding classes.
    """
    modem_classes = {}
    
    # Create a temporary directory to clone repositories
    with tempfile.TemporaryDirectory() as temp_dir:
        for repo_url in repo_urls:
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            repo_path = os.path.join(temp_dir, repo_name)
            _log.debug("Cloning git repository into %s...", repo_path)
            result = subprocess.run(
                ["git", "clone", "--branch", branch, repo_url, repo_path],
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
                for file in files:
                    if file.endswith(".py"):
                        file_path = os.path.join(root, file)
                        class_def = load_modem_class(file_path)
                        if class_def:
                            modem_classes[file.replace('.py', '')] = class_def
                            if download_path and os.path.isdir(download_path):
                                dest_path = os.path.join(download_path, file)
                                shutil.copy(file_path, dest_path)
                                _log.debug('Copied %s to %s', file, dest_path)

    return modem_classes


def load_modem_class(file_path: str) -> Type[NbntnBaseModem] | None:
    """
    Load a Python file and return the modem class if it subclasses NbntnModem.

    Args:
        file_path (str): Path to the Python file.

    Returns:
        Type[NbntnBaseModem] | None: The modem class if valid, else None.
    """
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

    # Look for subclasses of NbntnModem
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type) and issubclass(attr, NbntnBaseModem) and
            attr is not NbntnBaseModem):
            return attr

    return None
