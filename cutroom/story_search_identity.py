"""Scoped source identity and immutable local-model identity for Story reuse.

The model lookup reads inventory metadata only. It never starts a daemon,
generates text, warms a model or downloads weights. An unavailable identity
disables persistent reuse rather than substituting a mutable model tag.
"""
from __future__ import annotations

import copy
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from .ai_runtime import open_ollama, read_ollama_json
from .config import Settings


_SOURCE_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("cutroom_story_search_source", default=None)
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}")
_MODEL_DIGEST = re.compile(r"[0-9A-Fa-f]{64}")
_TAGS_RESPONSE_BYTES = 2 * 1024 * 1024


@contextmanager
def story_search_source_context(identity: dict[str, Any]) -> Iterator[None]:
    """Scope a deep source snapshot to this execution context, restoring nesting."""
    if not isinstance(identity, dict):
        raise TypeError("Story source identity must be a dictionary.")
    token = _SOURCE_CONTEXT.set(copy.deepcopy(identity))
    try:
        yield
    finally:
        _SOURCE_CONTEXT.reset(token)


def current_story_search_source() -> dict[str, Any] | None:
    """Return a detached snapshot; callers never receive the stored dictionary."""
    value = _SOURCE_CONTEXT.get()
    return copy.deepcopy(value) if value is not None else None


def _normalized_model_name(value: Any) -> str | None:
    if not isinstance(value, str) or _MODEL_NAME.fullmatch(value) is None:
        return None
    return value.removesuffix(":latest")


def local_story_model_identity(settings: Settings, model: str) -> dict[str, str] | None:
    """Read the selected local model's immutable digest within fixed I/O bounds.

    Names are matched exactly and case-sensitively, except that a terminal
    ``:latest`` is equivalent to the untagged name. No row without a complete
    SHA-256 digest, or multiple matching inventory rows, may authorize reuse.
    Existing local transport enforces loopback, no proxies/redirects and a total
    socket deadline. Failures return no identity and never fall back to a tag.
    """
    try:
        ai = getattr(settings, "ai", None)
    except Exception:
        return None
    if not isinstance(ai, dict):
        return None
    connection = ai.get("cloud_connection", {})
    if not isinstance(connection, dict) or connection.get("mode", "local") != "local":
        return None
    selected = _normalized_model_name(model)
    endpoint = ai.get("ollama_url", "http://127.0.0.1:11434")
    if selected is None or not isinstance(endpoint, str) or not endpoint or len(endpoint) > 2048:
        return None
    try:
        with open_ollama(endpoint.rstrip("/") + "/api/tags", timeout=2) as response:
            payload = read_ollama_json(response, _TAGS_RESPONSE_BYTES)
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            return None
        identity = None
        for row in payload["models"]:
            if not isinstance(row, dict):
                return None
            name = _normalized_model_name(row.get("name"))
            if name is None:
                return None
            if name != selected:
                continue
            if identity is not None:
                return None
            if "model" in row and _normalized_model_name(row["model"]) != selected:
                return None
            digest = row.get("digest")
            if not isinstance(digest, str) or _MODEL_DIGEST.fullmatch(digest) is None:
                return None
            identity = {"provider": "ollama", "model": selected, "digest": digest.lower()}
        return identity
    except Exception:
        # Persistent reuse is optional. Missing or untrustworthy metadata must
        # not turn a model tag into an immutable identity or block fresh work.
        return None
