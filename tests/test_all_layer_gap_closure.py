"""All-layer empty-space removal; executable with stdlib unittest as well as pytest.

No models, downloads, user projects or web server are needed. FFmpeg coverage
uses only generated color/tone media in a temporary directory.
"""
from __future__ import annotations

import copy
import json
import math
from array import array
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.captions import build_ass
from cutroom.config import DEFAULTS, Settings
from cutroom.projects import ProjectStore
from cutroom.render import build_filter_graph, project_caption_items
from cutroom.media_render import library_input_args
from cutroom.source_tracks import timeline_duration

ASSET = "asset_" + "a" * 32


def project(kind="video", fps=30):
    return {
        "id": "project_012345abcdef", "settings": {"fps": fps, "editorial_effects": False},
        "sources": {"A": {"duration": 4, "width": 160, "height": 90, "has_audio": True,
                            "relative_path": "source.mp4"}},
        "assets": {ASSET: {"id": ASSET, "kind": kind, "status": "ready", "duration": 3,
                            "has_audio": True, "width": 160, "height": 90, "path": "extra.mp4"}},
        "draft": {"keep_ranges": [{"start": 0, "end": 4}],
                  "camera_plan": [{"start": 0, "end": 4, "camera": "A"}]},
        "analysis": {"audio_source": "A", "transcript": {"segments": [
            {"id": "speech", "start": 2.5, "end": 3.5, "text": "Source words"}]}},
        "manual": {
            "sequence": {"version": 1, "duration": 12, "camera_plan": [
                {"start": 0, "end": 12, "camera": "A"}]},
            "source_tracks": {"A": [
                {"id": "first", "start": 2., "end": 4., "source_start": 0.},
                {"id": "last", "start": 8., "end": 10., "source_start": 2.}], "B": []},
            "media_clips": [{"id": "media_" + "a" * 32, "asset_id": ASSET,
                "start": 4., "end": 6., "source_start": .5, "video_source_start": .5,
                "speed": 1., "volume_db": -3., "muted": False, "audio_enabled": True,
                "role": "voice", "fade_in": .1, "fade_out": .2,
                "x": 0., "y": 0., "w": 1., "h": 1., "fit": "cover", "motion": "none"}],
            "text_clips": [{"id": "text_" + "a" * 32, "kind": "caption", "start": 8.5,
                "end": 9.5, "text": "Custom words", "style": "clean", "position": "bottom", "scale": 100}],
        },
    }


def close(value, **extra):
    return apply_manual_edit(value, {"action": "sequence_close_gaps", **extra})


class AllLayerGapClosureTests(unittest.TestCase):
    def test_three_gaps_move_every_layer_preserving_all_other_fields(self):
        for kind in ("video", "audio", "image"):
            with self.subTest(kind=kind):
                value = project(kind)
                before = copy.deepcopy(value)
                close(value)
                self.assertEqual(timeline_duration(value), 6)
                for key, shift in (("media_clips", 2), ("text_clips", 4)):
                    self.assertEqual(value["manual"][key], [
                        {**row, "start": row["start"] - shift, "end": row["end"] - shift}
                        for row in before["manual"][key]])
                for key in ("sources", "assets", "analysis"):
                    self.assertEqual(value[key], before[key])
                self.assertEqual([(c["start"], c["end"], c["source_start"]) for c in
                                  value["manual"]["source_tracks"]["A"]], [(0, 2, 0), (4, 6, 2)])
                self.assertEqual(value["manual"]["sequence"]["camera_plan"][-1]["end"], 6)

    def test_json_roundtrip_one_undo_and_redo_restore_all_layers(self):
        value = project()
        before = copy.deepcopy(value["manual"])
        close(value)
        self.assertEqual(value["manual"]["history"]["undo_count"], 1)
        after = copy.deepcopy(value["manual"])
        value = json.loads(json.dumps(value))
        apply_manual_edit(value, {"action": "undo"})
        for key in ("source_tracks", "sequence", "media_clips", "text_clips"):
            self.assertEqual(value["manual"][key], before[key])
        apply_manual_edit(value, {"action": "redo"})
        for key in ("source_tracks", "sequence", "media_clips", "text_clips"):
            self.assertEqual(value["manual"][key], after[key])
        snapshot = copy.deepcopy(value)
        close(value)
        self.assertEqual(value, snapshot, "Repeated close must consume no history")

    def test_close_insert_append_save_reopen_and_full_history_preserve_each_layer(self):
        value = project()
        before = copy.deepcopy(value)
        close(value)
        selected = {"asset_id": ASSET, "source_start": .25, "source_end": 1.5}
        apply_manual_edit(value, {"action": "media_insert", "start": 4., **selected})
        inserted = copy.deepcopy(value["manual"]["media_clips"][-1])
        self.assertEqual((inserted["start"], inserted["end"], inserted["source_start"]), (4., 5.25, .25))
        self.assertEqual(value["manual"]["text_clips"][0]["start"], 5.75)
        self.assertEqual(value["manual"]["source_tracks"]["A"][-1]["start"], 5.25)
        apply_manual_edit(value, {"action": "media_append", **selected})
        self.assertEqual(timeline_duration(value), 8.5)
        self.assertEqual(value["manual"]["media_clips"][-1]["start"], 7.25)
        self.assertEqual(value["manual"]["history"]["undo_count"], 3)
        for key in ("sources", "assets", "analysis"):
            self.assertEqual(value[key], before[key])
        # Save/reopen serialization must retain the three independent commands.
        value = json.loads(json.dumps(value))
        after = copy.deepcopy(value["manual"])
        unchanged = copy.deepcopy(value)
        close(value)
        self.assertEqual(value, unchanged, "A fully occupied integrated edit is a no-op")
        for _ in range(3):
            apply_manual_edit(value, {"action": "undo"})
        for key in ("source_tracks", "sequence", "media_clips", "text_clips"):
            self.assertEqual(value["manual"][key], before["manual"][key])
        for _ in range(3):
            apply_manual_edit(value, {"action": "redo"})
        for key in ("source_tracks", "sequence", "media_clips", "text_clips"):
            self.assertEqual(value["manual"][key], after[key])

    def test_spanning_music_and_titles_keep_occupied_time_even_when_muted(self):
        for field in ("media_clips", "text_clips"):
            for muted in ((True, False) if field == "media_clips" else (None,)):
                with self.subTest(field=field, muted=muted):
                    value = project()
                    value["manual"][field][0].update(start=0., end=12.)
                    if muted is not None:
                        value["manual"][field][0]["muted"] = muted
                    before = copy.deepcopy(value)
                    close(value)
                    self.assertEqual(value, before)

    def test_empty_source_lanes_keep_independent_layer_content(self):
        value = project()
        value["manual"]["source_tracks"]["A"] = []
        close(value)
        self.assertEqual(timeline_duration(value), 3)
        self.assertEqual([(c["start"], c["end"]) for c in value["manual"]["media_clips"]], [(0, 2)])
        self.assertEqual([(c["start"], c["end"]) for c in value["manual"]["text_clips"]], [(2, 3)])

    def test_locked_source_rejects_whole_transaction_without_history(self):
        value = project()
        value["manual"]["track_locks"] = {"A": True}
        before = copy.deepcopy(value)
        with self.assertRaisesRegex(ManualEditError, "locked"):
            close(value)
        self.assertEqual(value, before)

    def test_source_only_does_not_shift_layers_and_rejects_stranded_tail(self):
        value = project()
        before = copy.deepcopy(value)
        with self.assertRaisesRegex(ManualEditError, "shorten"):
            close(value, slot="A")
        self.assertEqual(value, before)
        value["sources"]["B"] = copy.deepcopy(value["sources"]["A"])
        value["manual"]["source_tracks"]["B"] = [{"id": "B", "start": 8., "end": 12., "source_start": 0.}]
        close(value, slot="A")
        for key in ("media_clips", "text_clips"):
            self.assertEqual(value["manual"][key], before["manual"][key])
        self.assertEqual(value["manual"]["source_tracks"]["B"][0]["start"], 8)

    def test_invalid_layer_timing_never_changes_anything(self):
        for patch in ({"start": -1}, {"end": 13}, {"start": True}, {"end": None},
                      {"start": 6, "end": 6}, {"start": "4"}):
            with self.subTest(patch=patch):
                value = project()
                value["manual"]["media_clips"][0].update(patch)
                before = copy.deepcopy(value)
                with self.assertRaises(ManualEditError):
                    close(value)
                self.assertEqual(value, before)

    def test_frame_length_gaps_are_closed_at_all_supported_rates(self):
        for fps in (24, 25, 30, 50, 60):
            with self.subTest(fps=fps):
                value = project(fps=fps)
                frame = round(1 / fps, 9)
                value["manual"]["source_tracks"] = {"A": [], "B": []}
                value["manual"]["media_clips"][0].update(start=frame, end=round(frame + 2, 9))
                value["manual"]["text_clips"] = []
                close(value)
                self.assertAlmostEqual(timeline_duration(value), 2, places=8)
                self.assertEqual(value["manual"]["media_clips"][0]["start"], 0)

    def test_edited_source_caption_follows_its_source_and_custom_caption(self):
        value = project()
        caption = project_caption_items(value, aligned=False)[0]
        value["manual"]["caption_overrides"] = {caption["id"]: {"text": "Corrected words"}}
        value["manual"]["caption_override_anchors"] = {caption["id"]: copy.deepcopy(caption["_caption_anchor"])}
        close(value)
        caption = next(row for row in project_caption_items(value, aligned=False) if row["text"] == "Corrected words")
        self.assertEqual((caption["start"], caption["end"]), (4.5, 5.5))
        self.assertEqual(value["manual"]["text_clips"][0]["start"], 4.5)

    def test_legacy_caption_wording_survives_first_materialization_with_or_without_layers(self):
        for layers in (True, False):
            with self.subTest(layers=layers):
                value = project()
                value["manual"].pop("sequence")
                value["sources"]["A"]["duration"] = 12
                value["draft"]["keep_ranges"] = [{"start": 0, "end": 12}]
                value["draft"]["camera_plan"] = [{"start": 0, "end": 12, "camera": "A"}]
                if not layers:
                    value["manual"]["media_clips"] = []
                    value["manual"]["text_clips"] = []
                item = project_caption_items(value, aligned=False)[0]
                apply_manual_edit(value, {"action": "caption_update", "caption_id": item["id"],
                                          "text": "Legacy correction", "style": "clean", "scale": 110})
                before = copy.deepcopy(value)
                close(value)
                caption = project_caption_items(value, aligned=False)[0]
                self.assertEqual(caption["text"], "Legacy correction")
                self.assertEqual(caption["scale"], 110)
                self.assertEqual(caption["_caption_anchor"], item["_caption_anchor"])
                self.assertEqual(caption["start"], 4.5 if layers else 2.5)
                self.assertFalse(value["manual"].get("caption_dormant_overrides"))
                apply_manual_edit(value, {"action": "undo"})
                self.assertNotIn("sequence", value["manual"])
                self.assertEqual(value["manual"]["source_tracks"], before["manual"]["source_tracks"])
                self.assertEqual(project_caption_items(value, aligned=False)[0]["text"], "Legacy correction")
                apply_manual_edit(value, {"action": "redo"})
                self.assertEqual(project_caption_items(value, aligned=False)[0]["_caption_anchor"], item["_caption_anchor"])

    def test_legacy_noop_and_rejection_never_persist_caption_lineage(self):
        for outcome in ("noop", "locked", "merge"):
            with self.subTest(outcome=outcome):
                value = project()
                value["manual"].pop("sequence")
                value["sources"]["A"]["duration"] = 12
                value["draft"]["keep_ranges"] = [{"start": 0, "end": 12}]
                value["draft"]["camera_plan"] = [{"start": 0, "end": 12, "camera": "A"}]
                if outcome == "merge":
                    value["analysis"]["transcript"]["segments"] = [
                        {"id": "speech", "start": 0., "end": 4., "text": "Original whole sentence"}]
                    value["manual"]["media_clips"][0].update(start=10., end=12.)
                item = project_caption_items(value, aligned=False)[0]
                apply_manual_edit(value, {"action": "caption_update", "caption_id": item["id"], "text": "Legacy correction"})
                if outcome == "noop":
                    value["manual"]["media_clips"][0].update(start=0., end=12.)
                elif outcome == "locked":
                    value["manual"]["track_locks"] = {"A": True}
                before = copy.deepcopy(value)
                if outcome == "noop":
                    close(value)
                else:
                    with self.assertRaisesRegex(ManualEditError, "locked" if outcome == "locked" else "merge or change"):
                        close(value)
                self.assertEqual(value, before)

    def test_legacy_camera_boundaries_subdivide_but_do_not_change_edited_caption_ownership(self):
        value = project()
        value["manual"].pop("sequence")
        value["sources"]["A"]["duration"] = 12
        value["draft"]["keep_ranges"] = [{"start": 0, "end": 12}]
        value["draft"]["camera_plan"] = [
            {"start": 0, "end": 9, "camera": "A"}, {"start": 9, "end": 12, "camera": "A"}]
        item = project_caption_items(value, aligned=False)[0]
        apply_manual_edit(value, {"action": "caption_update", "caption_id": item["id"],
                                  "text": "Keep the whole correction", "scale": 110})
        close(value)
        caption = project_caption_items(value, aligned=False)[0]
        self.assertEqual(caption["text"], "Keep the whole correction")
        self.assertEqual((caption["start"], caption["end"], caption["scale"]), (4.5, 5.5, 110))
        self.assertFalse(value["manual"].get("caption_dormant_overrides"))
        self.assertEqual(caption["_caption_anchor"]["spans"], [
            {"origin": "last", "start": 2.5, "end": 3.}, {"origin": "last", "start": 3., "end": 3.5}])

    def test_retimed_caption_rejects_atomically_instead_of_losing_its_words(self):
        value = project()
        caption = project_caption_items(value, aligned=False)[0]
        apply_manual_edit(value, {"action": "caption_update", "caption_id": caption["id"],
                                 "start": 10.5, "end": 11.5, "text": "My timed text"})
        before = copy.deepcopy(value)
        with self.assertRaisesRegex(ManualEditError, "custom timing"):
            close(value)
        self.assertEqual(value, before)
        self.assertEqual(project_caption_items(value, aligned=False)[0]["text"], "My timed text")

    def test_active_caption_alternative_is_preserved_and_noop_is_allowed(self):
        from cutroom.caption_alternatives import FORMAT, binding, register, geometry, status
        value = project()
        value["sources"]["A"]["generation"] = "synthetic-source"
        key = register(value, {"format": FORMAT, "binding": binding(value), "source_interval": [0., 4.],
            "transcript": {"segments": [{"id": "alt", "start": 2.5, "end": 3.5, "text": "Chosen alternate"}]}})
        value["manual"]["caption_alternative"] = {"id": key, "geometry": geometry(value)}
        before = copy.deepcopy(value)
        with self.assertRaisesRegex(ManualEditError, "alternative caption"):
            close(value)
        self.assertEqual(value, before)
        self.assertEqual(status(value)["active_id"], key)
        value["manual"]["text_clips"][0].update(start=0., end=12.)
        before = copy.deepcopy(value)
        close(value)
        self.assertEqual(value, before)

    def test_uncertain_caption_ownership_is_not_silently_reassigned(self):
        for key, content in (("caption_dormant_overrides", [{"edit": {"text": "Saved words"}}]),
                             ("caption_overrides", {"unknown": {"text": "Saved words"}})):
            with self.subTest(key=key):
                value = project()
                value["manual"][key] = content
                before = copy.deepcopy(value)
                with self.assertRaisesRegex(ManualEditError, "uncertain ownership"):
                    close(value)
                self.assertEqual(value, before)

    def test_closing_a_sentence_gap_never_merges_or_spreads_partial_caption_edits(self):
        for count in (1, 2):
            with self.subTest(edited_captions=count):
                value = project()
                value["analysis"]["transcript"]["segments"] = [
                    {"id": "speech", "start": 0., "end": 4., "text": "Original whole sentence"}]
                value["manual"]["media_clips"][0].update(start=10., end=12.)
                items = project_caption_items(value, aligned=False)
                self.assertEqual(len(items), 2)
                for item, text in list(zip(items, ("Edited first half", "Edited last half")))[:count]:
                    apply_manual_edit(value, {"action": "caption_update", "caption_id": item["id"], "text": text})
                before = copy.deepcopy(value)
                with self.assertRaisesRegex(ManualEditError, "merge or change"):
                    close(value)
                self.assertEqual(value, before)

    def test_save_reopen_and_stale_revision_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(copy.deepcopy(DEFAULTS), root, root, root / "projects",
                                root / "exports", root / "cache", "ffmpeg", "ffprobe")
            store = ProjectStore(settings)
            initial = store.create("Synthetic gap closure")
            value = {**initial, **project(), "id": initial["id"]}
            value["assets"][ASSET]["path"] = f"media/assets/{ASSET}/original.mp4"
            store.save(value)
            revision = store.load(value["id"])["revision"]
            store.update(value["id"], close, expected_revision=revision)
            reopened = store.load(value["id"])
            self.assertEqual(timeline_duration(reopened), 6)
            self.assertEqual(reopened["manual"]["media_clips"][0]["start"], 2)
            selected = {"asset_id": ASSET, "source_start": .25, "source_end": 1.5}
            for action, extra in (("media_insert", {"start": 4.}), ("media_append", {})):
                current_revision = store.load(value["id"])["revision"]
                store.update(value["id"], lambda current: apply_manual_edit(
                    current, {"action": action, **selected, **extra}), expected_revision=current_revision)
            reopened = store.load(value["id"])
            self.assertEqual(timeline_duration(reopened), 8.5)
            self.assertEqual(reopened["manual"]["history"]["undo_count"], 3)
            self.assertEqual(reopened["manual"]["media_clips"][-1]["source_start"], .25)
            self.assertEqual(reopened["manual"]["text_clips"][0]["start"], 5.75)
            before = store.state_path(value["id"]).read_bytes()
            with self.assertRaisesRegex(RuntimeError, "revision_conflict"):
                store.update(value["id"], close, expected_revision=revision)
            self.assertEqual(store.state_path(value["id"]).read_bytes(), before)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe unavailable")
    def test_encoded_picture_and_sound_follow_all_layer_gap_closure(self):
        def run(args):
            return subprocess.run(args, check=True, capture_output=True, timeout=30).stdout
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "color=red:s=160x90:r=30:d=2[r];color=blue:s=160x90:r=30:d=2[b];[r][b]concat=n=2:v=1:a=0",
                 "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
                 "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(root / "source.mp4")])
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=lime:s=160x90:r=30:d=3",
                 "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=3",
                 "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(root / "extra.mp4")])
            value = project()
            close(value)
            caption_ass = root / "captions.ass"
            build_ass({}, [], caption_ass, 160, 90, text_clips=value["manual"]["text_clips"])
            self.assertIn("0:00:04.50,0:00:05.50", caption_ass.read_text(encoding="utf-8"))
            graph, maps, _ = build_filter_graph(value, 160, 90, caption_ass)
            output = root / "result.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(root / "source.mp4"),
                 *library_input_args(value, root), "-filter_complex", graph, *maps,
                 "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-threads", "2", str(output)])
            duration = float(json.loads(run(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(output)]))["format"]["duration"])
            self.assertAlmostEqual(duration, 6, delta=.04)
            for at, dominant in ((1, 0), (3, 1), (5, 2)):
                frame = run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(output), "-frames:v", "1",
                             "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
                pixel = frame[(5 * 160 + 5) * 3:(5 * 160 + 5) * 3 + 3]
                self.assertGreater(pixel[dominant], 200)
                self.assertLess(max(pixel[i] for i in range(3) if i != dominant), 50)
            # The custom caption is actually burned at its translated time,
            # not merely present as a moved row in the project JSON.
            white_counts = []
            for at in (4.2, 4.8, 5.8):
                frame = run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(output), "-frames:v", "1",
                             "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
                white_counts.append(sum(min(frame[i:i + 3]) > 180 for i in range(0, len(frame), 3)))
            self.assertLess(white_counts[0], 5)
            self.assertGreater(white_counts[1], 20)
            self.assertLess(white_counts[2], 5)
            data = array("f", run(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
            def level(at, frequency):
                window = data[round(at * 48000):round(at * 48000) + 4800]
                return 2 * abs(sum(sample * complex(math.cos(2 * math.pi * frequency * i / 48000),
                    math.sin(2 * math.pi * frequency * i / 48000)) for i, sample in enumerate(window))) / len(window)
            for at, tone, absent in ((1, 440, 880), (3, 880, 440), (5, 440, 880)):
                self.assertGreater(level(at, tone), .025)
                self.assertLess(level(at, absent), .005)

            # Exercise the combined update: a saved source range uses the same
            # existing insert/append actions after the new all-layer closure.
            selected = {"asset_id": ASSET, "source_start": .25, "source_end": 1.5}
            apply_manual_edit(value, {"action": "media_insert", "start": 4., **selected})
            apply_manual_edit(value, {"action": "media_append", **selected})
            build_ass({}, [], caption_ass, 160, 90, text_clips=value["manual"]["text_clips"])
            self.assertIn("0:00:05.75,0:00:06.75", caption_ass.read_text(encoding="utf-8"))
            graph, maps, _ = build_filter_graph(value, 160, 90, caption_ass)
            output = root / "integrated.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(root / "source.mp4"),
                 *library_input_args(value, root), "-filter_complex", graph, *maps,
                 "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-threads", "2", str(output)])
            duration = float(json.loads(run(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(output)]))["format"]["duration"])
            self.assertAlmostEqual(duration, 8.5, delta=.04)
            for at, dominant in ((1, 0), (3, 1), (4.5, 1), (6, 2), (8, 1)):
                frame = run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(output), "-frames:v", "1",
                             "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
                pixel = frame[(5 * 160 + 5) * 3:(5 * 160 + 5) * 3 + 3]
                self.assertGreater(pixel[dominant], 200)
                self.assertLess(max(pixel[i] for i in range(3) if i != dominant), 50)
                if at == 6:
                    self.assertGreater(sum(min(frame[i:i + 3]) > 180 for i in range(0, len(frame), 3)), 20)
            data = array("f", run(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
            for at, tone, absent in ((1, 440, 880), (3, 880, 440), (4.5, 880, 440), (6, 440, 880), (8, 880, 440)):
                self.assertGreater(level(at, tone), .025)
                self.assertLess(level(at, absent), .005)


if __name__ == "__main__":
    unittest.main()
