import json
import wave
from pathlib import Path

SFX = Path(__file__).resolve().parents[1] / "web" / "sfx"


def test_catalog_lists_existing_short_mono_wavs():
    catalog = json.loads((SFX / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["version"] == 1 and len(catalog["sounds"]) >= 6
    for sound in catalog["sounds"]:
        with wave.open(str(SFX / sound["file"])) as item:
            assert item.getnchannels() == 1 and item.getframerate() == 44_100
            seconds = item.getnframes() / item.getframerate()
        assert abs(seconds - sound["seconds"]) < 0.01 and 0 < seconds <= 3
