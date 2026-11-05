"""Read-only estimates for derived media, using the existing volume identity.

Capacity is a point-in-time estimate, not a reservation or codec-size guarantee.
Original uploads are already on disk and are never counted/copied a second time.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

from .upload_storage import RESERVE_BYTES, filesystem_id

MiB = 1024**2


def readable_bytes(value: int) -> str:
    return f"{value / 1024**3:.2f} GiB" if value >= 1024**3 else f"{value / MiB:.1f} MiB"


class WorkingStorageError(RuntimeError):
    """Safe user-facing preparation failure; no source media is removed."""
    def __init__(self, operation: str, row: dict[str, Any]):
        self.storage_plan = {"operation": operation, "filesystems": [row], "estimate": True}
        super().__init__(
            f"Not enough working space for {operation} at {', '.join(row['locations'])}: "
            f"{readable_bytes(row['disk_free_bytes'])} free; approximately "
            f"{readable_bytes(row['required_bytes'])} for processing plus "
            f"{readable_bytes(row['reserve_bytes'])} safety reserve is required. "
            "The transfer may be complete, but processing is not. Your original is preserved. "
            "Free space on this drive and retry.")
        self.diagnostic = {"outcome": "technical_error", "reason": "insufficient_storage",
                           "applied_to_timeline": False}


def preparation_bytes(metadata: dict[str, Any], *, transcode: bool, height: int = 720,
                      crf: int = 27) -> int:
    """Conservative planning allowance, without allocating input-sized buffers.

    16 Mbps at 720p plus audio, scaled for wider/taller previews and lower CRF.
    Images allow uncompressed RGBA plus overhead; exact codec size is unknown.
    """
    overhead = 16 * MiB  # thumbnails, waveform/profile JSON and atomic commits
    if not transcode:
        return overhead
    kind = metadata.get("kind", "video")
    width, source_height = max(1, int(metadata.get("width") or 1280)), max(1, int(metadata.get("height") or 720))
    if kind == "image":
        scale = min(1., 4096 / width)
        return overhead + math.ceil(width * source_height * scale**2 * 5)
    duration = float(metadata.get("duration") or 0)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("Cannot estimate working space without valid media duration")
    if kind == "audio":
        return overhead + math.ceil(duration * 192_000 / 8 * 1.5)
    scale = min(1., max(1, height) / source_height)
    pixels = width * source_height * scale**2
    quality = max(1., 2 ** ((27 - max(0, min(51, crf))) / 6))
    return overhead + math.ceil(duration * (2_000_000 * max(1., pixels / (1280 * 720)) * quality + 24_000))


def require_working_space(allocations: list[tuple[str, Path, int]], *, operation: str,
                          reserve_bytes: int = RESERVE_BYTES) -> dict[str, Any]:
    volumes = {}
    for role, requested, size in allocations:
        requested = Path(requested).resolve()
        existing = requested
        while not existing.exists() and existing.parent != existing:
            existing = existing.parent
        volume = filesystem_id(existing)
        row = volumes.setdefault(volume, {"filesystem": volume, "location": str(existing),
            "roles": [], "locations": [], "required_bytes": 0, "reserved_bytes": 0,
            "reserve_bytes": max(0, int(reserve_bytes))})
        row["roles"].append(role);row["locations"].append(str(requested))
        row["required_bytes"] += max(0, int(size))
    for row in volumes.values():
        free = max(0, int(shutil.disk_usage(row["location"]).free))
        row.update(disk_free_bytes=free, available_bytes=max(0, free-row["reserve_bytes"]))
        if free < row["required_bytes"] + row["reserve_bytes"]:
            raise WorkingStorageError(operation, row)
    return {"operation": operation, "estimate": True, "filesystems": list(volumes.values()),
            "scope": "derived_media_only_original_already_present"}
