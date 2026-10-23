"""Lexical native-I/O paths, after the caller has validated containment.

Windows' extended-length filesystem spelling avoids the legacy MAX_PATH
limit for an individual operation.  This does not change system settings,
resolve links, check ownership, or make an untrusted path safe.  Keep roots
and descendants in the same spelling when computing relative metadata.
"""
from __future__ import annotations

import ntpath
import os
from pathlib import Path
import re

_WINDOWS = os.name == "nt"


def _extended_windows_path(value: str) -> str:
    """Normalize an absolute drive/UNC filesystem path without filesystem I/O."""
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("A nonempty absolute filesystem path without NUL is required")
    value = value.replace("/", "\\")
    if value.startswith("\\\\.\\"):
        raise ValueError("Windows device paths are not supported")
    if value.startswith("\\\\?\\"):
        remainder = value[4:]
        if remainder[:4].lower() == "unc\\":
            value = "\\\\" + remainder[4:]
        elif re.match(r"^[A-Za-z]:\\", remainder):
            value = remainder
        else:
            raise ValueError("Only absolute drive or UNC filesystem paths are supported")
    drive, tail = ntpath.splitdrive(value)
    if re.fullmatch(r"[A-Za-z]:", drive) and tail.startswith("\\"):
        return "\\\\?\\" + ntpath.normpath(value)
    if drive.startswith("\\\\"):
        share = drive[2:].split("\\")
        if len(share) == 2 and all(share) and not any(part in {".", ".."} for part in share):
            return "\\\\?\\UNC\\" + ntpath.normpath(value)[2:]
    raise ValueError("An absolute drive or UNC filesystem path is required")


def native_io_path(path: str | os.PathLike[str]) -> Path:
    """Return an absolute Path suitable for native I/O, without resolving it.

    The caller must first validate its ordinary path and containment.  Never
    persist the returned absolute spelling in project metadata or URLs.
    """
    value = os.fspath(path)
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("A nonempty absolute filesystem path without NUL is required")
    if _WINDOWS:
        return Path(_extended_windows_path(value))
    result = Path(value)
    if not result.is_absolute():
        raise ValueError("An absolute filesystem path is required")
    return result
