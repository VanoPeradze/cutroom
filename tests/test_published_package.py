import hashlib
import io
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_published_package as published


@pytest.mark.parametrize("case", ["valid", "changed", "oversized", "http", "wrong_build", "existing"])
@pytest.mark.parametrize("historical", [False, True])
def test_exact_public_download_verification(tmp_path, monkeypatch, case, historical):
    content = b"approved zip bytes"
    release = {"layout": "windows-mac-folders-v1", "bytes": len(content),
               "sha256": hashlib.sha256(content).hexdigest(), "url": "https://example.invalid/package.zip",
               "build_id": "expected"}
    metadata = tmp_path / "release.json"
    metadata.write_text(json.dumps(release))
    response = io.BytesIO({"changed": b"X" + content[1:], "oversized": content + b"X"}.get(case, content))
    response.url = "http://example.invalid/file" if case == "http" else release["url"]
    def fetch(request, timeout):
        assert request.full_url == release["url"]
        assert request.get_header("User-agent").startswith("CUTROOM-Mac-validation/")
        return response
    monkeypatch.setattr(published.urllib.request, "urlopen", fetch)
    verified = []
    historical_pin = tmp_path / "historical-windows.json" if historical else None
    def verify(path, *, windows_baseline=None):
        assert windows_baseline == historical_pin
        verified.append(path.read_bytes())
        return {"build_id": "wrong" if case == "wrong_build" else "expected"}
    monkeypatch.setattr(published, "verify_package", verify)
    target = tmp_path / "download.zip"
    if case == "existing":
        target.write_bytes(b"keep this file")
    if case == "valid":
        assert published.download(metadata, target, windows_baseline=historical_pin) == target
        assert target.read_bytes() == content and verified == [content]
    else:
        with pytest.raises((ValueError, FileExistsError)):
            published.download(metadata, target, windows_baseline=historical_pin)
        if case == "existing":
            assert target.read_bytes() == b"keep this file"
        else:
            assert not target.exists()
        if case in {"changed", "oversized", "http"}:
            assert not verified
