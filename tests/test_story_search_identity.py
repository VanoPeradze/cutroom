"""Source contexts are isolated; immutable model inventory uses mocked I/O only."""
from __future__ import annotations

import asyncio
import copy
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from cutroom import story_search_identity as identity


MODEL = "qwen3.5:4b"
DIGEST = "2a654d98" + "a1" * 28
OTHER_DIGEST = "b2" * 32


def settings(**ai_patch):
    return SimpleNamespace(ai={"ollama_url": "http://127.0.0.1:11434", **ai_patch})


def tags(name=MODEL, digest=DIGEST, **extra):
    return {"models": [{"name": name, "model": name, "digest": digest, **extra}]}


@pytest.fixture(autouse=True)
def no_real_transport(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append((args, kwargs))
        pytest.fail("Identity tests must never access a real Ollama endpoint")

    monkeypatch.setattr(identity, "open_ollama", forbidden)
    return attempts


@pytest.fixture
def mocked_tags(monkeypatch):
    calls = []
    reads = []
    responses = []

    class Response(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    def install(payload=None, *, raw=None, error=None):
        body = raw if raw is not None else json.dumps(payload).encode("utf-8")

        @contextmanager
        def fake_open(endpoint, timeout):
            calls.append((endpoint, timeout))
            if error is not None:
                raise error
            with Response(body) as response:
                responses.append(response)
                yield response

        monkeypatch.setattr(identity, "open_ollama", fake_open)

    return install, calls, reads, responses


def test_source_context_snapshots_input_and_detaches_every_getter():
    source = {"fingerprints": {"source": "hash-A"}, "generations": ["generation-A", {"B": "generation-B"}]}
    original = copy.deepcopy(source)
    assert identity.current_story_search_source() is None

    with identity.story_search_source_context(source):
        source["fingerprints"]["source"] = "caller mutation"
        source["generations"][1]["B"] = "caller mutation"
        first = identity.current_story_search_source()
        assert first == original
        first["fingerprints"]["source"] = "getter mutation"
        first["generations"].append("extra")
        assert identity.current_story_search_source() == original

    assert identity.current_story_search_source() is None


def test_nested_source_context_restores_outer_snapshot_after_normal_exit_and_exception():
    outer = {"source": {"A": "outer"}}
    inner = {"source": {"A": "inner"}}
    with identity.story_search_source_context(outer):
        with identity.story_search_source_context(inner):
            assert identity.current_story_search_source() == inner
        assert identity.current_story_search_source() == outer
        with pytest.raises(RuntimeError, match="synthetic interruption"):
            with identity.story_search_source_context(inner):
                raise RuntimeError("synthetic interruption")
        assert identity.current_story_search_source() == outer
    assert identity.current_story_search_source() is None


def test_empty_context_is_distinct_from_no_context():
    with identity.story_search_source_context({}):
        assert identity.current_story_search_source() == {}
    assert identity.current_story_search_source() is None


@pytest.mark.parametrize("invalid", [None, [], "source", 1, True])
def test_invalid_context_input_does_not_replace_an_existing_scope(invalid):
    with identity.story_search_source_context({"source": "outer"}):
        with pytest.raises(TypeError):
            with identity.story_search_source_context(invalid):
                pytest.fail("Invalid context entered")
        assert identity.current_story_search_source() == {"source": "outer"}


def test_simultaneous_threads_keep_nested_source_contexts_separate():
    rendezvous = threading.Barrier(2)

    def worker(name):
        baseline = identity.current_story_search_source()
        expected = {"source": {"generation": name}}
        with identity.story_search_source_context(expected):
            rendezvous.wait(timeout=2)
            snapshot = identity.current_story_search_source()
            snapshot["source"]["generation"] = "detached mutation"
            rendezvous.wait(timeout=2)
            assert identity.current_story_search_source() == expected
        assert identity.current_story_search_source() == baseline
        return expected

    with identity.story_search_source_context({"source": "parent"}):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, name) for name in ("A", "B")]
            assert [future.result(timeout=4) for future in futures] == [
                {"source": {"generation": "A"}}, {"source": {"generation": "B"}},
            ]
        assert identity.current_story_search_source() == {"source": "parent"}
    assert identity.current_story_search_source() is None


def test_interleaved_async_contexts_inherit_outer_scope_without_cross_task_mutation():
    async def exercise():
        async def worker(name):
            assert identity.current_story_search_source() == {"source": "outer"}
            with identity.story_search_source_context({"source": {"task": name}}):
                await asyncio.sleep(0)
                assert identity.current_story_search_source() == {"source": {"task": name}}
            assert identity.current_story_search_source() == {"source": "outer"}

        with identity.story_search_source_context({"source": "outer"}):
            await asyncio.gather(worker("A"), worker("B"))
            assert identity.current_story_search_source() == {"source": "outer"}

    asyncio.run(exercise())
    assert identity.current_story_search_source() is None


def test_local_model_identity_reads_only_bounded_tags_inventory_and_closes_response(mocked_tags):
    install, calls, reads, responses = mocked_tags
    install(tags())

    result = identity.local_story_model_identity(settings(), MODEL)

    assert result == {"provider": "ollama", "model": MODEL, "digest": DIGEST}
    assert calls == [("http://127.0.0.1:11434/api/tags", 2)]
    assert reads == [2 * 1024 * 1024 + 1]
    assert len(responses) == 1 and responses[0].closed


@pytest.mark.parametrize(("selected", "installed", "canonical"), [
    ("qwen3.5", "qwen3.5:latest", "qwen3.5"),
    ("qwen3.5:latest", "qwen3.5", "qwen3.5"),
    ("qwen3.5:latest", "qwen3.5:latest", "qwen3.5"),
    (MODEL, MODEL, MODEL),
    ("registry.local:5000/team/model:4b", "registry.local:5000/team/model:4b", "registry.local:5000/team/model:4b"),
])
def test_selected_model_name_matches_exactly_except_terminal_latest(mocked_tags, selected, installed, canonical):
    install, _, _, _ = mocked_tags
    install(tags(name=installed))
    result = identity.local_story_model_identity(settings(), selected)
    assert result == {"provider": "ollama", "model": canonical, "digest": DIGEST}


def test_same_mutable_tag_with_new_digest_has_different_immutable_identity(mocked_tags):
    install, calls, _, _ = mocked_tags
    install(tags())
    before = identity.local_story_model_identity(settings(), MODEL)
    install(tags(digest=OTHER_DIGEST))
    after = identity.local_story_model_identity(settings(), MODEL)
    assert before["model"] == after["model"] == MODEL
    assert before["digest"] == DIGEST and after["digest"] == OTHER_DIGEST
    assert before != after and len(calls) == 2


def test_digest_case_is_canonical_and_result_does_not_retain_response_metadata(mocked_tags):
    install, _, _, _ = mocked_tags
    install(tags(digest=DIGEST.upper(), details={"private": "private-metadata-sentinel"}))
    first = identity.local_story_model_identity(settings(), MODEL)
    assert first == {"provider": "ollama", "model": MODEL, "digest": DIGEST}
    first["digest"] = "caller mutation"
    assert identity.local_story_model_identity(settings(), MODEL)["digest"] == DIGEST
    assert "private-metadata-sentinel" not in json.dumps(first)


@pytest.mark.parametrize("digest", [None, "", "a" * 63, "a" * 65, "g" * 64, "sha256:" + DIGEST,
                                     DIGEST + "\n", True, 123, {}, []],
                         ids=["none", "empty", "short", "long", "nonhex", "prefixed",
                              "newline", "boolean", "integer", "mapping", "list"])
def test_missing_malformed_or_nonimmutable_digest_never_falls_back_to_model_tag(mocked_tags, digest):
    install, _, _, _ = mocked_tags
    install(tags(digest=digest))
    assert identity.local_story_model_identity(settings(), MODEL) is None


@pytest.mark.parametrize("payload", [
    None, [], {}, {"models": None}, {"models": {}}, {"models": []},
    {"models": [None]}, {"models": [{"model": MODEL, "digest": DIGEST}]},
    {"models": [{"name": MODEL}]},
    {"models": [{"name": True, "digest": DIGEST}]},
    {"models": [{"name": MODEL, "model": "different-model", "digest": DIGEST}]},
])
def test_malformed_inventory_does_not_authorize_persistent_reuse(mocked_tags, payload):
    install, _, _, _ = mocked_tags
    install(payload)
    assert identity.local_story_model_identity(settings(), MODEL) is None


@pytest.mark.parametrize("installed", ["Qwen3.5:4b", "qwen3.5:9b", "other/qwen3.5:4b", "qwen3.5:4b-extra"])
def test_no_case_prefix_basename_or_alternate_tag_fallback(mocked_tags, installed):
    install, _, _, _ = mocked_tags
    install(tags(name=installed))
    assert identity.local_story_model_identity(settings(), MODEL) is None


@pytest.mark.parametrize("second_digest", [DIGEST, OTHER_DIGEST])
def test_multiple_matching_rows_are_ambiguous_even_with_the_same_digest(mocked_tags, second_digest):
    install, _, _, _ = mocked_tags
    install({"models": [{"name": MODEL, "digest": DIGEST}, {"name": MODEL, "digest": second_digest}]})
    assert identity.local_story_model_identity(settings(), MODEL) is None


def test_latest_alias_duplicate_is_ambiguous(mocked_tags):
    install, _, _, _ = mocked_tags
    install({"models": [{"name": "qwen3.5", "digest": DIGEST},
                        {"name": "qwen3.5:latest", "digest": DIGEST}]})
    assert identity.local_story_model_identity(settings(), "qwen3.5") is None


@pytest.mark.parametrize("mode", ["groq", "openai-compatible", "cloud", "LOCAL", None, True])
def test_cloud_or_unknown_mode_returns_none_before_any_transport(no_real_transport, mode):
    assert identity.local_story_model_identity(settings(cloud_connection={"mode": mode}), MODEL) is None
    assert no_real_transport == []


@pytest.mark.parametrize("bad", [None, [], True, "local"])
def test_malformed_cloud_connection_returns_none_before_any_transport(no_real_transport, bad):
    assert identity.local_story_model_identity(settings(cloud_connection=bad), MODEL) is None
    assert no_real_transport == []


@pytest.mark.parametrize("model", [None, "", " model", "model ", "model name", "model\nname", True, 42, {}, "x" * 513],
                         ids=["none", "empty", "leading-space", "trailing-space", "embedded-space",
                              "newline", "boolean", "integer", "mapping", "oversized-name"])
def test_invalid_selected_model_returns_none_before_any_transport(no_real_transport, model):
    assert identity.local_story_model_identity(settings(), model) is None
    assert no_real_transport == []


@pytest.mark.parametrize("bad", [None, SimpleNamespace(), SimpleNamespace(ai=None), SimpleNamespace(ai=[])])
def test_missing_or_malformed_ai_settings_return_none(no_real_transport, bad):
    assert identity.local_story_model_identity(bad, MODEL) is None
    assert no_real_transport == []


def test_corrupt_settings_property_disables_reuse_before_transport(no_real_transport):
    class CorruptSettings:
        @property
        def ai(self):
            raise KeyError("missing AI configuration")

    assert identity.local_story_model_identity(CorruptSettings(), MODEL) is None
    assert no_real_transport == []


@pytest.mark.parametrize("endpoint", [None, "", True, 42, "x" * 2049],
                         ids=["none", "empty", "boolean", "integer", "oversized-url"])
def test_malformed_endpoint_returns_none_before_transport(no_real_transport, endpoint):
    assert identity.local_story_model_identity(settings(ollama_url=endpoint), MODEL) is None
    assert no_real_transport == []


@pytest.mark.parametrize("error", [OSError("offline"), TimeoutError("deadline"), ValueError("invalid local endpoint")])
def test_inventory_transport_failure_disables_reuse_without_model_generation(mocked_tags, error):
    install, calls, _, _ = mocked_tags
    install(tags(), error=error)
    assert identity.local_story_model_identity(settings(), MODEL) is None
    assert calls == [("http://127.0.0.1:11434/api/tags", 2)]


@pytest.mark.parametrize("raw", [b"not json", b'{"models":', b" " * (2 * 1024 * 1024 + 1)],
                         ids=["invalid-json", "truncated-json", "oversized-body"])
def test_malformed_or_oversized_body_is_closed_and_disables_reuse(mocked_tags, raw):
    install, _, reads, responses = mocked_tags
    install(raw=raw)
    assert identity.local_story_model_identity(settings(), MODEL) is None
    assert reads == [2 * 1024 * 1024 + 1]
    assert len(responses) == 1 and responses[0].closed
