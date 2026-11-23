"""Content provenance and ready-preview repair admission."""

import hashlib
import json
import math
import re
import stat
from pathlib import Path
from .asset_preparation import PreparationCacheError

FIELD = "_original_content_proof"
META = ("duration", "width", "height", "has_audio")


class PreviewRepairError(PreparationCacheError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def original_path(root, asset):
    if (
        not isinstance(asset, dict)
        or not isinstance(asset.get("id"), str)
        or not re.fullmatch(r"asset_[0-9a-f]{32}", asset["id"])
    ):
        raise PreviewRepairError("original_unsafe", "Invalid original asset identity")
    relative = asset.get("path")
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise PreviewRepairError("original_unsafe", "Invalid original path")
    rel = Path(relative)
    if (
        rel.is_absolute()
        or rel.drive
        or any(x in {"..", "."} for x in rel.parts)
        or rel.parent != Path("media") / "assets" / asset["id"]
    ):
        raise PreviewRepairError(
            "original_unsafe", "Original is not owned by this asset"
        )
    current = Path(root).absolute()
    try:
        for part in [
            *reversed(current.parents),
            current,
            *[current / Path(*rel.parts[:i]) for i in range(1, len(rel.parts) + 1)],
        ]:
            info = part.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
            ):
                raise PreviewRepairError(
                    "original_unsafe", "Original path has a link or reparse point"
                )
        result = current / rel
        info = result.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PreviewRepairError(
                "original_unsafe",
                "Original must be an independently owned regular file",
            )
        return result
    except FileNotFoundError as exc:
        raise PreviewRepairError(
            "original_missing",
            "The saved original is unavailable; repair cannot relink it",
        ) from exc
    except OSError as exc:
        raise PreviewRepairError(
            "original_unavailable", "The saved original cannot be read safely"
        ) from exc


def make_proof(asset, identity):
    proof = {
        "version": 1,
        "path": asset["path"],
        "kind": asset["kind"],
        "size": identity["file"]["size"],
        "sha256": identity["file"]["sha256"],
        "metadata": {k: asset[k] for k in META},
    }
    return validate_proof(proof)


def validate_proof(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "path", "kind", "size", "sha256", "metadata"}
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise PreviewRepairError(
            "original_proof_invalid", "Original proof is invalid or unsupported"
        )
    if (
        not isinstance(value["path"], str)
        or not value["path"]
        or not isinstance(value["kind"], str)
        or value["kind"] not in {"audio", "video", "image"}
        or type(value["size"]) is not int
        or value["size"] <= 0
        or not isinstance(value["sha256"], str)
        or not re.fullmatch("[0-9a-f]{64}", value["sha256"])
    ):
        raise PreviewRepairError("original_proof_invalid", "Original proof is invalid")
    m = value["metadata"]
    if (
        not isinstance(m, dict)
        or set(m) != set(META)
        or type(m["has_audio"]) is not bool
        or any(
            type(m[k]) not in (int, float) or not math.isfinite(m[k]) or m[k] < 0
            for k in ("duration", "width", "height")
        )
    ):
        raise PreviewRepairError(
            "original_proof_invalid", "Original proof metadata is invalid"
        )
    if any(
        type(m[k]) is not int or not 0 <= m[k] <= 100000 for k in ("width", "height")
    ):
        raise PreviewRepairError(
            "original_proof_invalid", "Original dimensions must be bounded integers"
        )
    if (
        value["kind"] == "audio"
        and (m["width"] != 0 or m["height"] != 0 or not m["has_audio"])
    ) or (value["kind"] in {"video", "image"} and (m["width"] < 1 or m["height"] < 1)):
        raise PreviewRepairError(
            "original_proof_invalid",
            "Original dimensions or audio flag do not match its kind",
        )
    if (value["kind"] == "image" and (m["duration"] != 0 or m["has_audio"])) or (
        value["kind"] != "image" and not 0.08 <= m["duration"] <= 14400
    ):
        raise PreviewRepairError(
            "original_proof_invalid", "Original duration does not match its kind"
        )
    return value


def admit_proof(asset, key, identity):
    proof = make_proof(asset, identity)
    validate_proof(proof)
    if FIELD in asset:
        saved = validate_proof(asset[FIELD])
        if any(saved[name] != proof[name] for name in ("size", "sha256")):
            raise PreviewRepairError(
                "original_changed",
                "Original does not match its saved content proof; repair refused",
            )
        if saved != proof:
            raise PreviewRepairError(
                "original_unverifiable",
                "Original content matches, but its saved binding or metadata cannot be verified; repair refused",
            )
    elif asset.get("preparation_identity") != key:
        raise PreviewRepairError(
            "original_unverifiable",
            "Original identity is unverifiable for this legacy asset; repair refused",
        )
    return proof


def repair_asset(context, project_id, asset_id, store, settings, binding):
    from .media_library import prepare_asset
    from .jobs import JobCancelled

    try:
        return prepare_asset(
            context, project_id, asset_id, store, settings, repair_binding=binding
        )
    except JobCancelled:
        raise
    except Exception as exc:
        current = exc
        for _ in range(8):
            if isinstance(current, PreviewRepairError):
                if current is exc:
                    raise
                raise current from exc
            current = current.__cause__
            if current is None:
                break
        raise PreviewRepairError(
            "preview_repair_failed",
            "Preview repair did not finish. The saved asset binding was kept; check storage and retry explicitly.",
        ) from exc


def preview_version(asset):
    """Opaque browser cache identity; content-proof stamping is deliberately excluded."""
    identity = asset.get("preparation_identity")
    path = asset.get("preview_path")
    if asset.get("status") != "ready":
        return None
    identity = identity if isinstance(identity, str) and identity else None
    path = path if isinstance(path, str) and path else None
    return hashlib.sha256(json.dumps([identity, path], separators=(",", ":")).encode()).hexdigest()[:24]
