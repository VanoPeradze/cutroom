"""Select exactly three pinned assets from an unpublished GitHub review release.

This transport guard only reads local JSON and Git objects. It never downloads,
writes files, invokes application code, or treats release metadata as proof of
the downloaded bytes. The offline candidate gate must still verify those bytes.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import re
import sys


REPOSITORY = "VanoPeradze/cutroom"
API_ROOT = "https://api.github.com/repos/" + REPOSITORY
MAX_METADATA_BYTES = 1024 * 1024
MAX_ID = (1 << 63) - 1


def _adapter():
    path = Path(__file__).with_name("native_review_candidate.py")
    spec = importlib.util.spec_from_file_location("cutroom_review_transport_identity", path)
    if spec is None or spec.loader is None:
        raise ValueError("The private review identity adapter is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _identifier(value: object) -> bool:
    return type(value) is int and 0 < value <= MAX_ID


def expected_assets(record: dict) -> dict[str, dict]:
    """Return exact review names for the matching, pinned 1.2 or 1.3 Beta builds."""
    versions = set()
    for platform in ("windows", "combined"):
        build_id = record[platform]["build_id"]
        match = (re.fullmatch(r"CUTROOM-(1\.[23])-beta-[A-Za-z0-9.-]+", build_id)
                 if isinstance(build_id, str) else None)
        _require(match is not None, "Review asset naming requires a pinned 1.2 or 1.3 Beta build ID")
        versions.add(match[1])
    _require(len(versions) == 1, "Windows and combined review build versions differ")
    version = versions.pop()
    short = record["source"]["commit"][:7]
    return {
        f"CUTROOM-{version}-Beta-Windows-review-{short}.zip": record["windows"],
        f"CUTROOM-{version}-Beta-combined-review-{short}.zip": record["combined"],
        f"SOURCE-{short}.zip": {
            "bytes": record["source"]["archive_bytes"],
            "sha256": record["source"]["archive_sha256"],
        },
    }


def validate_metadata(metadata: dict, record: dict, release_id: int,
                      repository: str = REPOSITORY) -> tuple[tuple[int, str], ...]:
    """Validate untrusted metadata after the caller has Git-bound the record."""
    _require(repository == REPOSITORY, "Review transport is restricted to VanoPeradze/cutroom")
    _require(_identifier(release_id), "Release ID must be a positive integer")
    _require(isinstance(metadata, dict), "Release metadata must be an object")
    _require(_identifier(metadata.get("id")) and metadata["id"] == release_id,
             "Release ID differs from the requested release")
    _require(metadata.get("url") == f"{API_ROOT}/releases/{release_id}",
             "Release API URL differs from the selected repository and ID")
    _require(metadata.get("draft") is True and "published_at" in metadata
             and metadata["published_at"] is None, "Review release must be unpublished and draft")
    commit = record["source"]["commit"]
    _require(metadata.get("tag_name") == "cutroom-review-" + commit[:7],
             "Release tag differs from the reviewed source")
    _require(metadata.get("target_commitish") == commit,
             "Release target must be the full reviewed source commit")
    pins = expected_assets(record)
    assets = metadata.get("assets")
    _require(isinstance(assets, list) and len(assets) == len(pins),
             "Draft release must contain exactly the three reviewed ZIPs")
    selected: dict[str, int] = {}
    ids: set[int] = set()
    for asset in assets:
        _require(isinstance(asset, dict), "Release asset must be an object")
        name, asset_id = asset.get("name"), asset.get("id")
        _require(isinstance(name, str) and name in pins and name not in selected,
                 "Unexpected or duplicate review asset name")
        _require(_identifier(asset_id) and asset_id not in ids,
                 "Invalid or duplicate review asset ID")
        _require(asset.get("url") == f"{API_ROOT}/releases/assets/{asset_id}",
                 "Asset API URL differs from the selected repository and ID")
        _require(asset.get("state") == "uploaded", "Review asset upload is incomplete")
        _require(type(asset.get("size")) is int and asset["size"] == pins[name]["bytes"],
                 "Review asset size differs from the committed pin")
        if "digest" in asset:
            _require(asset["digest"] == "sha256:" + pins[name]["sha256"],
                     "Review asset digest differs from the committed SHA-256 pin")
        selected[name] = asset_id
        ids.add(asset_id)
    _require(set(selected) == set(pins), "Review asset inventory differs from the committed record")
    return tuple((selected[name], name) for name in pins)


def select_assets(metadata_path: Path, record_path: Path, release_id: int,
                  repo: Path, repository: str = REPOSITORY) -> tuple[tuple[int, str], ...]:
    """Git-bind a reviewed record and return safe asset IDs/names without writes."""
    adapter = _adapter()
    verifier = adapter._load_verifier()
    repo = Path(repo).resolve()
    record_path = Path(record_path).absolute()
    record, provenance = adapter._committed_record(record_path, repo, verifier)
    verifier._record(record)
    metadata_path = Path(metadata_path).absolute()
    _require(metadata_path.is_file() and metadata_path.stat().st_size <= MAX_METADATA_BYTES,
             "Missing or oversized draft-release metadata")
    raw = verifier._read(metadata_path)
    rows = validate_metadata(verifier.parse_json(raw), record, release_id, repository)
    current, current_provenance = adapter._committed_record(record_path, repo, verifier)
    _require(current == record and current_provenance == provenance,
             "Committed review record changed during metadata validation")
    _require(verifier._read(metadata_path) == raw, "Draft-release metadata changed during validation")
    return rows


def _release_id(value: str) -> int:
    if re.fullmatch(r"[1-9][0-9]{0,18}", value) is None or not _identifier(int(value)):
        raise argparse.ArgumentTypeError("release ID must be a positive decimal integer")
    return int(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--release-id", type=_release_id, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--repository", default=REPOSITORY)
    args = parser.parse_args(argv)
    try:
        rows = select_assets(args.metadata, args.record, args.release_id, args.repo, args.repository)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("Review asset metadata rejected: " + str(error), file=sys.stderr)
        return 1
    for asset_id, name in rows:
        print(f"{asset_id}\t{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
