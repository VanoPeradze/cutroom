"""Start CUTROOM with the Windows setup's Unicode-safe tool paths."""
from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PATHS_VAR = "CUTROOM_RUNTIME_PATHS_B64"


def restore_runtime_paths() -> None:
    """Restore paths saved as ASCII-safe UTF-8 data by setup_windows.ps1."""
    encoded = os.environ.pop(RUNTIME_PATHS_VAR, "")
    if not encoded:
        return  # Older installs rely on the inherited PATH.
    try:
        if len(encoded) > 32768:
            raise ValueError("saved tool paths are too long")
        data = base64.b64decode(encoded.encode("ascii"), validate=True)
        paths = json.loads(data.decode("utf-8"))
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise ValueError("saved tool paths must be a list of strings")
        if any(not os.path.isabs(item) or "\x00" in item or os.pathsep in item for item in paths):
            raise ValueError("saved tool paths must be absolute directories")
    except (UnicodeError, ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise RuntimeError("Saved tool paths are invalid; run Repair CUTROOM and try again.") from exc

    seen: set[str] = set()
    usable: list[str] = []
    for item in paths:
        key = os.path.normcase(os.path.normpath(item))
        if key not in seen and os.path.isdir(item):
            usable.append(item)
            seen.add(key)
    if usable:
        inherited = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(usable + ([inherited] if inherited else []))


def main() -> int:
    targets = {"preflight": ROOT / "scripts" / "preflight.py", "server": ROOT / "server.py"}
    if len(sys.argv) != 2 or sys.argv[1] not in targets:
        print("Usage: windows_runtime.py {preflight|server}", file=sys.stderr)
        return 2
    try:
        restore_runtime_paths()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    target = targets[sys.argv[1]]
    sys.argv = [str(target)]
    sys.path.insert(0, str(ROOT))
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
