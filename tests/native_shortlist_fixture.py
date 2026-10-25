"""Generated-source understanding through plan_edit, stopping before inference.

This captures actual product inputs, not a manually injected candidate plan.
Private qualification recordings remain outside committed test fixtures.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cutroom import intelligence as story
from tests.portable_support.source_fixture import source_fixture, understanding_reply


class CapturedPrecision(BaseException):
    pass


def capture_native_shortlist():
    source = source_fixture()
    segments = copy.deepcopy(source["segments"])
    result = {"model_calls": 0, "understanding_replay_stages": [], "understanding_payloads": [],
              "raw_understanding_replies": {}, "source_kind": "generated_text_only"}
    original_options = story._passage_options
    original_request = story._passage_option_request

    def observe(candidates, rows, chapters, plan, brief, *args, **kwargs):
        result.update(rows=copy.deepcopy(rows), candidates=copy.deepcopy(candidates), chapters=copy.deepcopy(chapters),
                      plan=copy.deepcopy(plan), brief=copy.deepcopy(brief))
        options = original_options(candidates, rows, chapters, plan, brief, *args, **kwargs)
        result["enumerated"] = copy.deepcopy(options)
        return options

    def observe_request(settings, options, *args):
        result["assessment_receipt"] = copy.deepcopy(options["receipt"])
        return original_request(settings, options, *args)

    def replay(_settings, payload, *_args):
        system = payload["messages"][0]["content"]
        for needle, stage in [("first pass", "01_summary"), ("global story analyst", "02_outline"), ("Story Producer", "03_plan")]:
            if needle in system:
                result["understanding_replay_stages"].append(stage)
                result["understanding_payloads"].append(copy.deepcopy(payload))
                reply = understanding_reply(payload)
                result["raw_understanding_replies"][stage] = copy.deepcopy(reply)
                return reply
        data = json.loads(payload["messages"][-1]["content"])
        if "passage_candidates" not in data:
            raise AssertionError("Unexpected model stage in deterministic product fixture")
        result["precision_payload"] = copy.deepcopy(payload)
        result["presented"] = data["passage_candidates"]
        raise CapturedPrecision()

    def forbidden(*_a, **_k):
        raise AssertionError("Network/model access forbidden in deterministic replay")

    brief = {"goal": "short", "language": "en", "target_duration": 60., "duration_mode": "target",
             "performance_mode": "balanced", "instruction": source["brief"]["instruction"],
             "allow_extractive_rough_cut": False}
    with patch.object(story, "_passage_options", observe), patch.object(story, "_passage_option_request", observe_request), patch.object(story, "_call_ollama_story_pass", replay), \
            patch.object(story, "open_ollama", forbidden), patch.object(story, "_ready_story_model_status",
            lambda *_: {"selected_model": "qwen3.5:4b", "ready": True}):
        try:
            story.plan_edit(segments, SimpleNamespace(ai={"performance_mode": "balanced", "source_quality_assessment":False}), brief)
        except CapturedPrecision:
            pass
        else:
            raise AssertionError("Product did not reach the actual precision boundary")
    assert segments == source["segments"]
    assert result["understanding_replay_stages"] == ["01_summary", "02_outline", "03_plan"]
    return result
