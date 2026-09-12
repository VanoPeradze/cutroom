from __future__ import annotations

from cutroom.captions import build_ass, build_srt


def test_captions_keep_words_clipped_at_manual_cut_boundaries(tmp_path):
    from cutroom.captions import _caption_entries

    transcript = {"segments": [{"start": 0, "end": 3, "text": "hello there friend", "words": [
        {"start": 0.4, "end": 1.0, "word": "hello"},
        {"start": 1.1, "end": 1.5, "word": "there"},
        {"start": 1.6, "end": 2.4, "word": "friend"},
    ]}]}
    keep = [{"start": 0.6, "end": 2.2}]
    entries = _caption_entries(transcript, keep)
    assert len(entries) == 1
    assert entries[0][0] == 0.0
    assert round(entries[0][1], 3) == 1.6
    assert entries[0][2] == "hello there friend"
    srt = build_srt(transcript, keep, tmp_path / "boundary.srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,600" in srt
    assert "hello there friend" in srt


def test_captions_do_not_bridge_removed_speech_or_restore_removed_words(tmp_path):
    from cutroom.captions import _caption_entries

    transcript = {"segments": [{"start": 0, "end": 2, "text": "first removed last", "words": [
        {"start": 0.0, "end": 0.4, "word": "first"},
        {"start": 0.5, "end": 0.7, "word": "removed"},
        {"start": 0.8, "end": 1.2, "word": "last"},
    ]}]}
    keep = [{"start": 0.0, "end": 0.45}, {"start": 0.75, "end": 1.25}]
    entries = _caption_entries(transcript, keep)
    assert [entry[2] for entry in entries] == ["first", "last"]
    # The segment's nominal span includes silence after the final word. It must
    # not resurrect all its words when only that silence is kept.
    silent_keep = [{"start": 1.3, "end": 2.0}]
    assert _caption_entries(transcript, silent_keep) == []
    assert build_srt(transcript, silent_keep, tmp_path / "silent.srt").read_text(encoding="utf-8") == ""


def test_srt_retimes_after_cut(tmp_path):
    transcript = {"segments": [
        {"start": 0, "end": 2, "text": "First", "words": [{"start": 0, "end": 1, "word": "First"}]},
        {"start": 4, "end": 6, "text": "Second", "words": [{"start": 4, "end": 5, "word": "Second"}]},
    ]}
    target = build_srt(transcript, [{"start": 0, "end": 2}, {"start": 4, "end": 6}], tmp_path / "captions.srt")
    text = target.read_text(encoding="utf-8")
    assert "00:00:02,000 --> 00:00:03,000" in text
    assert "Second" in text


def test_ass_burn_captions_retime_hebrew_after_cuts(tmp_path):
    transcript = {"segments": [
        {"start": 0, "end": 2, "text": "שלום לכולם", "words": [
            {"start": 0, "end": .8, "word": "שלום"}, {"start": .9, "end": 1.5, "word": "לכולם"},
        ]},
        {"start": 4, "end": 6, "text": "זה החלק החשוב", "words": [
            {"start": 4, "end": 4.5, "word": "זה"}, {"start": 4.6, "end": 5.1, "word": "החלק"}, {"start": 5.2, "end": 5.8, "word": "החשוב"},
        ]},
    ]}
    target = build_ass(transcript, [{"start": 0, "end": 2}, {"start": 4, "end": 6}], tmp_path / "captions.ass", 1080, 1920)
    text = target.read_text(encoding="utf-8-sig")
    assert "שלום לכולם" in text
    assert "זה החלק החשוב" in text
    assert "Dialogue: 0,0:00:02.00,0:00:03.80" in text


def test_ass_layout_metadata_is_optional_and_unknown_rows_preserve_default_output(tmp_path):
    transcript = {"segments": [
        {"start": 0, "end": 2, "text": "Default position", "words": []},
    ]}
    keep_ranges = [{"start": 0, "end": 2}]
    omitted = build_ass(transcript, keep_ranges, tmp_path / "omitted.ass", 1080, 1920)
    explicit_none = build_ass(transcript, keep_ranges, tmp_path / "none.ass", 1080, 1920, None)
    unknown = build_ass(
        transcript,
        keep_ranges,
        tmp_path / "unknown.ass",
        1080,
        1920,
        [{"start": 0, "end": 2, "layout": "{\\an7}"}],
    )

    assert omitted.read_bytes() == explicit_none.read_bytes() == unknown.read_bytes()
    text = omitted.read_text(encoding="utf-8-sig")
    assert "\\pos(" not in text
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Default position" in text


def test_ass_layout_ranges_follow_source_time_across_cuts_and_split_boundaries(tmp_path):
    transcript = {"segments": [
        {"start": 0, "end": 8, "text": "כתובית רציפה", "words": []},
    ]}
    keep_ranges = [{"start": 0, "end": 2}, {"start": 4, "end": 8}]
    # ``camera`` mirrors the field already present on render-plan rows.
    layout_ranges = [
        {"start": 0, "end": 1, "camera": "A"},
        {"start": 1, "end": 2, "camera": "embedded_stack"},
        {"start": 4, "end": 5, "camera": "embedded_stack"},
        {"start": 5, "end": 8, "camera": "stacked"},
    ]
    target = build_ass(
        transcript,
        keep_ranges,
        tmp_path / "layout-cut.ass",
        1080,
        1920,
        layout_ranges=layout_ranges,
    )
    dialogue = [line for line in target.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue:")]

    assert dialogue == [
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,כתובית רציפה",
        r"Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\an8\pos(540,653)}כתובית רציפה",
        r"Dialogue: 0,0:00:02.00,0:00:03.00,Default,,0,0,0,,{\an8\pos(540,653)}כתובית רציפה",
        r"Dialogue: 0,0:00:03.00,0:00:06.00,Default,,0,0,0,,{\an8\pos(540,1421)}כתובית רציפה",
    ]


def test_ass_overlapping_layout_rows_use_latest_start_at_exact_boundaries(tmp_path):
    transcript = {"segments": [
        {"start": 0, "end": 4, "text": "Boundary", "words": []},
    ]}
    target = build_ass(
        transcript,
        [{"start": 0, "end": 4}],
        tmp_path / "overlap.ass",
        1080,
        1920,
        layout_ranges=[
            {"start": 0, "end": 4, "layout": "stacked"},
            {"start": 1, "end": 3, "layout": "embedded_stack"},
        ],
    )
    dialogue = [line for line in target.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue:")]

    assert dialogue == [
        r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\an8\pos(540,1421)}Boundary",
        r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\an8\pos(540,653)}Boundary",
        r"Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,{\an8\pos(540,1421)}Boundary",
    ]


def test_ass_layout_override_preserves_rtl_text_and_escapes_ass_control_text(tmp_path):
    transcript = {"segments": [
        {"start": 0, "end": 1, "text": "שלום مرحبا {\\an7} C:\\tmp", "words": []},
    ]}
    target = build_ass(
        transcript,
        [{"start": 0, "end": 1}],
        tmp_path / "escaped.ass",
        720,
        1280,
        layout_ranges=[
            {"start": 0, "end": 1, "layout": "{\\an7}"},
            {"start": 0, "end": 1, "layout": "stacked"},
        ],
    )
    text = target.read_text(encoding="utf-8-sig")

    assert "שלום مرحبا" in text
    assert r"{\an8\pos(360,947)}" in text
    assert r"\{\\an7\} C:\\tmp" in text
    assert ",,{\\an7}" not in text


def test_render_graph_can_burn_ass_into_final_video(tmp_path):
    from cutroom.render import build_filter_graph
    project = {
        "sources": {"A": {"duration": 5, "width": 640, "height": 360, "has_audio": True}, "B": None},
        "settings": {"aspect": "9:16", "resolution": "720"},
        "analysis": {"sync": None, "vision": {}, "transcript": {"segments": []}},
        "manual": {"crop": {}},
        "draft": {"keep_ranges": [{"start": 0, "end": 5}], "camera_plan": [{"start": 0, "end": 5, "camera": "A"}]},
    }
    ass = tmp_path / "captions.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    graph, maps, has_audio = build_filter_graph(project, 720, 1280, ass)
    assert "ass=filename='" in graph
    assert "[vfinal]" in graph
    assert maps == ["-map", "[vfinal]", "-map", "[aout]"]
    assert has_audio is True


def test_segment_only_captions_survive_partial_cut(tmp_path):
    from cutroom.captions import build_srt
    transcript = {"segments": [
        {"start": 1.0, "end": 5.0, "text": "Segment without word timestamps", "words": []},
    ]}
    target = build_srt(transcript, [{"start": 0, "end": 2.5}, {"start": 4.0, "end": 6.0}], tmp_path / "partial.srt")
    text = target.read_text(encoding="utf-8")
    assert text.count("Segment without word timestamps") == 2
    assert "00:00:01,000 --> 00:00:02,500" in text
    assert "00:00:02,500 --> 00:00:03,500" in text


def test_ass_caption_controls_apply_safe_preset_position_scale_and_word_limit(tmp_path):
    words = [
        {"start": index * 0.25, "end": index * 0.25 + 0.2, "word": word}
        for index, word in enumerate("one two three four five six seven eight".split())
    ]
    transcript = {"segments": [{"start": 0, "end": 2, "text": "unused", "words": words}]}
    target = build_ass(
        transcript,
        [{"start": 0, "end": 2}],
        tmp_path / "controlled.ass",
        1080,
        1920,
        layout_ranges=[{"start": 0, "end": 2, "layout": "stacked"}],
        caption_style="boxed",
        caption_position="top",
        caption_scale=125,
        words_per_caption=3,
    )
    text = target.read_text(encoding="utf-8-sig")
    dialogue = [line for line in text.splitlines() if line.startswith("Dialogue:")]

    assert len(dialogue) == 3
    assert dialogue[0].endswith("one two three")
    assert dialogue[-1].endswith("seven eight")
    assert "Style: Default,Arial,90," in text
    assert ",3,11,0,8,42,42," in text
    assert "\\pos(" not in text


def test_srt_word_limit_creates_readable_short_caption_events(tmp_path):
    words = [
        {"start": index * 0.3, "end": index * 0.3 + 0.25, "word": word}
        for index, word in enumerate("one two three four five".split())
    ]
    target = build_srt(
        {"segments": [{"start": 0, "end": 1.5, "text": "unused", "words": words}]},
        [{"start": 0, "end": 2}],
        tmp_path / "short-events.srt",
        words_per_caption=2,
    )
    text = target.read_text(encoding="utf-8")

    assert text.count(" --> ") == 3
    assert "one two" in text
    assert "three four" in text
    assert "five" in text
