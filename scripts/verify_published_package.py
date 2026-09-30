"""Download and verify the exact public release before testing it on macOS."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.request

from build_universal_package import verify_package


def download(release_path: Path, destination: Path) -> Path:
    release = json.loads(release_path.read_text(encoding="utf-8"))
    if (release.get("layout") != "windows-mac-folders-v1"
            or not isinstance(release.get("bytes"), int)
            or not 0 < release["bytes"] <= 10 * 1024 * 1024
            or not re.fullmatch(r"[a-f0-9]{64}", release.get("sha256", ""))
            or not release.get("url", "").startswith("https://")):
        raise ValueError("Invalid published release metadata")
    request = urllib.request.Request(release["url"], headers={
        "User-Agent": "CUTROOM-Mac-validation/1.1 (+https://github.com/VanoPeradze/cutroom)",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        if not response.url.startswith("https://"):
            raise ValueError("Published release redirected away from HTTPS")
        data = response.read(release["bytes"] + 1)
    if len(data) != release["bytes"] or hashlib.sha256(data).hexdigest() != release["sha256"]:
        raise ValueError("Published release checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="cutroom-published-verify-") as directory:
        staged = Path(directory) / "release.zip"
        staged.write_bytes(data)
        manifest = verify_package(staged)
        if manifest["build_id"] != release["build_id"]:
            raise ValueError("Published release build ID mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(data)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=Path(__file__).resolve().parents[1] / "website/release.json")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    print(download(options.release, options.output))
