"""
Root-level conftest — patches pathlib.Path before pytest directory traversal.

The sandbox denies os.stat() on .env* files. This monkey-patch must execute
before pytest's collection phase encounters .env in this directory.
The test-level conftest (tests/conftest.py) loads too late.
"""

import pathlib as _pathlib

_original_is_file = _pathlib.Path.is_file
_original_is_dir = _pathlib.Path.is_dir
_original_stat = _pathlib.Path.stat


def _safe_is_file(self, *args, **kwargs):
    if ".env" in self.name:
        return False
    return _original_is_file(self, *args, **kwargs)


def _safe_is_dir(self, *args, **kwargs):
    if ".env" in self.name:
        return False
    return _original_is_dir(self, *args, **kwargs)


def _safe_stat(self, *args, **kwargs):
    if ".env" in self.name:
        raise FileNotFoundError(f"Sandbox-blocked: {self}")
    return _original_stat(self, *args, **kwargs)


_pathlib.Path.is_file = _safe_is_file
_pathlib.Path.is_dir = _safe_is_dir
_pathlib.Path.stat = _safe_stat
