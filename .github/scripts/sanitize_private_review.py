"""Retain only bounded, non-media results from the existing native review."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Expected native report and new sanitized output")
    source, target = map(Path, sys.argv[1:])
    report = json.loads(source.read_text(encoding="utf-8"))
    features = report["features"]
    fresh = report["installation"]["empty_app_install"]
    recovery = report["installation"]["missing_pip_recovery"]
    if (report["verdict"] != "passed_private_native_review_checks"
            or report["public_pins_unchanged"] is not True
            or features["features"]["skipped"] != 0
            or fresh["status"] != "passed" or recovery["status"] != "passed"):
        raise RuntimeError("Native private review did not satisfy its existing gates")
    clean = {"verdict": report["verdict"], "published": report["published"],
             "qualified_for_release": report["qualified_for_release"],
             "public_pins_unchanged": report["public_pins_unchanged"],
             "architecture": features["architecture"],
             "candidate_source_commit": features["candidate_source_commit"],
             "combined_sha256": features["archive"]["sha256"],
             "features_passed": features["features"]["passed"], "features_skipped": 0,
             "fresh_install": fresh["status"], "restart_persistence": fresh["restart_persistence"],
             "portrait": fresh["portrait"], "landscape": fresh["landscape"],
             "source_audio_and_caption_checks": fresh["source_audio_and_caption_checks"],
             "missing_pip_recovery": recovery["status"],
             "human_acceptance": report["human_acceptance"],
             "transcription": fresh["transcription"]["status"],
             "manual_finder_gatekeeper_test": fresh["manual_finder_gatekeeper_test"]}
    with target.open("x", encoding="utf-8") as output:
        json.dump(clean, output, indent=2)
        output.write("\n")
    print(json.dumps(clean, indent=2))


if __name__ == "__main__":
    main()
