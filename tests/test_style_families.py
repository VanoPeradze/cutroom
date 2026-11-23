from __future__ import annotations

from pathlib import Path

from cutroom.auto_style import recommend_style
from cutroom.director import _cut_candidates, _is_hesitation
from cutroom.edit_styles import (
    EDIT_STYLES,
    enrich_brief_with_style,
    get_edit_style,
    public_edit_styles,
    public_style_families,
    style_family,
)

LEGACY_IDS = {
    "smart", "stream_highlights", "competitive_clutch", "reaction_burst", "funny_moments",
    "stream_commentary", "stream_story", "chill_story", "clean_vod", "gameplay_youtube",
}


def test_five_families_cover_every_style_exactly_once():
    families = public_style_families()
    assert [family["id"] for family in families] == ["auto", "highlights", "talking", "story", "youtube_long"]
    variants = [variant["style"] for family in families for variant in family["variants"]]
    assert sorted(variants) == sorted(style["id"] for style in EDIT_STYLES)
    assert len(variants) == len(set(variants))
    assert all(family["default_style"] == family["variants"][0]["style"] for family in families)


def test_every_legacy_style_id_still_resolves_to_itself():
    # Saved projects keep their exact style: nothing is renamed or migrated.
    for style_id in LEGACY_IDS:
        assert get_edit_style(style_id, strict=True)["id"] == style_id
    assert style_family("competitive_clutch") == "highlights"
    assert style_family("clean_vod") == "youtube_long"
    assert style_family("unknown-old-value") == "auto"


def test_public_styles_name_their_family_and_variant():
    styles = {style["id"]: style for style in public_edit_styles()}
    assert styles["chill_story"]["family"] == "story"
    assert styles["chill_story"]["variant_label"]["en"] == "Natural"
    assert all("guidance" not in style for style in styles.values())


def test_families_are_offered_for_matching_goals_only():
    goals = {family["id"]: set(family["goals"]) for family in public_style_families()}
    assert "youtube" in goals["auto"] and "short" in goals["auto"]
    assert goals["youtube_long"] == {"youtube", "clean"}
    assert "youtube" not in goals["highlights"]


def test_new_talking_styles_are_executable_and_safe():
    talking = get_edit_style("talking_clips", strict=True)
    assert talking["defaults"]["goal"] == "short"
    assert talking["defaults"]["caption_style"] == "highlight"
    assert talking["selection_policy"]["moment_unit"] == "complete_thought"
    explainer = get_edit_style("youtube_explainer", strict=True)
    assert explainer["defaults"]["goal"] == "youtube"
    assert explainer["selection_policy"]["chronology"] == "strict"
    for style in (talking, explainer):
        assert style["framing_policy"]["embedded_camera_requires_confirmation"] is True
        assert style["framing_policy"]["allow_single_source_duplication"] is False


def test_source_context_reaches_story_as_advisory_background_only():
    enriched = enrich_brief_with_style({"edit_style": "talking_clips", "source_context": "  Podcast with Dana   (host) "})
    assert "source_context" not in enriched
    context = enriched["style_profile"]["source_context"]
    assert context["text"] == "Podcast with Dana (host)"
    assert context["authority"] == "advisory_only"
    plain = enrich_brief_with_style({"edit_style": "talking_clips", "source_context": "   "})
    assert "source_context" not in plain["style_profile"]


def test_source_context_is_capped():
    enriched = enrich_brief_with_style({"source_context": "x" * 2000})
    assert len(enriched["style_profile"]["source_context"]["text"]) == 600


def test_hesitation_words_only():
    assert all(_is_hesitation(word) for word in ("um", "Ummm,", "uh-", "אממ", "אה"))
    assert not any(_is_hesitation(word) for word in ("like", "so", "אז", "ממש", "umbrella", ""))


def _segment(words):
    return {"id": "s1", "start": 0.0, "end": 3.0, "text": " ".join(w[0] for w in words), "fillers": [],
            "words": [{"word": word, "start": start, "end": end} for word, start, end in words]}


def test_isolated_mid_sentence_hesitation_is_cut():
    candidates = _cut_candidates([_segment([("so", 0.0, 0.3), ("um,", 0.5, 0.9), ("this", 1.1, 1.4), ("works", 1.4, 1.9)])],
                                 {"remove_ids": []}, "balanced")
    assert len(candidates) == 1
    cut = candidates[0]
    assert cut["reason"] == "filler" and cut["evidence"]["isolated_by_pause"] is True
    assert 0.3 < cut["start"] <= 0.5 and 0.9 <= cut["end"] < 1.1


def test_hesitation_glued_to_neighbours_or_meaningful_words_stay():
    glued = _segment([("so", 0.0, 0.3), ("um", 0.32, 0.6), ("this", 0.62, 1.0)])
    meaningful = _segment([("so", 0.0, 0.3), ("like", 0.6, 0.9), ("this", 1.2, 1.5)])
    assert _cut_candidates([glued], {"remove_ids": []}, "balanced") == []
    assert _cut_candidates([meaningful], {"remove_ids": []}, "balanced") == []
    assert _cut_candidates([_segment([("so", 0.0, 0.3), ("um", 0.5, 0.9), ("ok", 1.1, 1.4)])], {"remove_ids": []}, "gentle") == []


def _project(goal="short", segments=(), visual=None, duration=100.0):
    return {"settings": {"goal": goal}, "sources": {"A": {"duration": duration}},
            "analysis": {"segments": list(segments), **({"visual_moments": visual} if visual else {})}}


def _speech(seconds, speakers=None):
    rows = []
    for index in range(int(seconds // 5)):
        row = {"start": index * 5.0, "end": index * 5.0 + 5.0, "text": f"line {index}"}
        if speakers:
            row["speaker"] = speakers[index % len(speakers)]
        rows.append(row)
    return rows


def _gameplay(share):
    windows = []
    for index in range(10):
        screen = "gameplay" if index < round(share * 10) else "menu"
        windows.append({"start": index * 10.0, "end": index * 10.0 + 10.0, "score": 0.5, "screen": screen})
    return {"available": True, "windows": windows}


def test_recommendation_without_evidence_is_low_confidence_auto():
    advice = recommend_style(_project())
    assert advice["style"] == "smart" and advice["confidence"] == "low"


def test_recommendation_for_talk_and_gameplay():
    assert recommend_style(_project(segments=_speech(90)))["style"] == "talking_clips"
    assert recommend_style(_project(segments=_speech(90, ["A", "B"])))["confidence"] == "high"
    assert recommend_style(_project(segments=_speech(20), visual=_gameplay(0.8)))["style"] == "stream_highlights"
    assert recommend_style(_project("youtube", segments=_speech(90)))["style"] == "youtube_explainer"
    assert recommend_style(_project("youtube", visual=_gameplay(0.8)))["style"] == "gameplay_youtube"
    advice = recommend_style(_project("youtube", segments=_speech(10)))
    assert advice["style"] == "clean_vod" and advice["confidence"] == "low"
    assert set(advice["reason"]) == {"he", "en"}


def test_system_exposes_families_and_recommendation_endpoint(tmp_path: Path, monkeypatch):
    from cutroom.config import load_settings
    from server import create_app

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    client = create_app(load_settings()).test_client()
    system = client.get("/api/system").get_json()
    assert [family["id"] for family in system["style_families"]][0] == "auto"

    project = client.post("/api/projects", json={"name": "families"}).get_json()["project"]
    saved = client.patch(f"/api/projects/{project['id']}", json={"settings": {
        "edit_style": "youtube_explainer", "source_context": "Explainer about bread"},
        "expected_revision": project["revision"]})
    assert saved.status_code == 200
    assert saved.get_json()["project"]["settings"]["source_context"] == "Explainer about bread"
    too_long = client.patch(f"/api/projects/{project['id']}", json={"settings": {"source_context": "x" * 601}})
    assert too_long.status_code == 400

    advice = client.get(f"/api/projects/{project['id']}/style-recommendation?goal=youtube")
    assert advice.status_code == 200
    assert advice.get_json()["recommendation"]["style"] in {"clean_vod", "smart"}
    assert client.get(f"/api/projects/{project['id']}/style-recommendation?goal=nope").status_code == 400
