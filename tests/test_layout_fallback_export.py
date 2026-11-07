"""Safe automatic A-picture fallback; stdlib tests with real encoded output."""
from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import tempfile
import threading
import unittest
from array import array
from pathlib import Path
from unittest.mock import patch

from cutroom.config import DEFAULTS, Settings
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.render import (LayoutCoverageError, _effective_audio_slot, _render_plan,
                            composition_layout_coverage, require_layout_coverage, render_project)


def project(duration=90.):
    return {
        "id": "project_fallback", "name": "Synthetic fallback",
        "settings": {"fps": 30, "aspect": "16:9", "resolution": "720", "layout": "stacked",
                     "editorial_effects": False, "captions": True, "burn_captions": True},
        "sources": {slot: {"duration": duration, "video_duration": duration, "width": 160, "height": 90,
                           "has_audio": True, "relative_path": f"media/source-{slot}.mp4"} for slot in ("A", "B")},
        "draft": {"keep_ranges": [{"start": 0., "end": duration}],
                  "camera_plan": [{"start": 0., "end": duration, "camera": "stacked"}]},
        "manual": {
            "source_mixer": {"screen_slot": "A", "camera_slot": "B", "audio_slot": "A", "default_layout": "stacked"},
            "sequence": {"version": 1, "duration": duration, "camera_plan": [{"start": 0., "end": duration, "camera": "stacked"}]},
            "source_tracks": {"A": [{"id": "a", "start": 0., "end": duration, "source_start": 0.}], "B": []},
        },
    }


class LayoutFallbackTests(unittest.TestCase):
    def test_reported_zero_of_ninety_case_exports_automatically_without_mutating_edit(self):
        value = project()
        before = copy.deepcopy(value)
        notice = require_layout_coverage(value)
        self.assertEqual(notice["missing_seconds"], 90.)
        self.assertEqual(notice["mode"], "available_A")
        self.assertIn("B/split layout is absent", notice["warning"])
        self.assertFalse(composition_layout_coverage(value)["export_blocked"])
        self.assertEqual(_render_plan(value), [{"start": 0., "end": 90., "camera": "A"}])
        self.assertEqual(value, before)

    def test_partial_b_keeps_requested_layout_and_preserves_chosen_audio(self):
        value = project(4.)
        value["manual"]["source_tracks"]["B"] = [{"id": "b", "start": 1., "end": 3., "source_start": 0.}]
        value["manual"]["source_mixer"]["audio_slot"] = "B"
        before = copy.deepcopy(value)
        self.assertEqual(require_layout_coverage(value)["missing_seconds"], 2.)
        self.assertEqual(_render_plan(value), [{"start": 0., "end": 1., "camera": "A"},
                                             {"start": 1., "end": 3., "camera": "stacked"},
                                             {"start": 3., "end": 4., "camera": "A"}])
        self.assertEqual(_effective_audio_slot(value), "B")
        self.assertEqual(value, before)

    def test_complete_requested_layout_needs_no_warning(self):
        value = project(4.)
        value["manual"]["source_tracks"]["B"] = [{"id": "b", "start": 0., "end": 4., "source_start": 0.}]
        self.assertIsNone(require_layout_coverage(value))

    def test_missing_a_or_both_sources_does_not_create_black_or_fake_picture(self):
        for b_present in (True, False):
            value = project(4.)
            value["manual"]["source_tracks"]["A"] = []
            if b_present:
                value["manual"]["source_tracks"]["B"] = [{"id": "b", "start": 0., "end": 4., "source_start": 0.}]
            before = copy.deepcopy(value)
            with self.assertRaises(LayoutCoverageError):
                require_layout_coverage(value)
            self.assertEqual(value, before)

    def test_short_or_nonvideo_a_is_not_accepted_as_a_full_interval_replacement(self):
        for independent in (True, False):
            for invalid in ("short", "audio_only"):
                value = project(4.)
                if not independent:
                    value["manual"].pop("sequence")
                    value["manual"].pop("source_tracks")
                    value["manual"]["source_mixer"]["sync_offset"] = 10.
                if invalid == "short":
                    value["sources"]["A"]["video_duration"] = 2.
                else:
                    value["sources"]["A"].update(width=0, height=0)
                with self.assertRaises(LayoutCoverageError):
                    require_layout_coverage(value)

    def test_uncovered_interval_after_public_range_limit_still_blocks(self):
        value = project(70.)
        value["manual"]["source_tracks"]["A"] = [{"id": "a", "start": 0., "end": 68., "source_start": 0.}]
        value["manual"]["sequence"]["camera_plan"] = [
            {"start": float(i), "end": float(i+1), "camera": "stacked" if i % 2 == 0 else "A"} for i in range(70)]
        report = composition_layout_coverage(value)
        self.assertEqual(report["missing_range_count"], 35)
        self.assertEqual(len(report["missing_ranges"]), 32)
        with self.assertRaises(LayoutCoverageError):
            require_layout_coverage(value)

    def test_fractional_endpoints_follow_the_actual_output_frame_grid(self):
        for fps in (24, 30, 60):
            for duration in (4.001, 4.01, 4.017):
                for independent in (True, False):
                    value = project(duration)
                    value["settings"]["fps"] = fps
                    if not independent:
                        value["manual"].pop("sequence"); value["manual"].pop("source_tracks")
                        value["manual"]["source_mixer"]["sync_offset"] = 10.
                    self.assertIsNotNone(require_layout_coverage(value))
                    value["sources"]["A"]["video_duration"] = 3.9
                    with self.assertRaises(LayoutCoverageError):
                        require_layout_coverage(value)

    def test_legacy_explicit_audio_does_not_switch_recordings_for_missing_b(self):
        value = project(4.)
        value["manual"].pop("sequence"); value["manual"].pop("source_tracks")
        for offset in (-10., 10.):
            value["manual"]["source_mixer"].update(audio_slot="B", sync_offset=offset)
            self.assertIsNotNone(require_layout_coverage(value))
            self.assertEqual(_effective_audio_slot(value), "B")
        value["sources"]["B"]["has_audio"] = False
        self.assertIsNone(_effective_audio_slot(value))
        value["manual"]["source_mixer"].pop("audio_slot")
        self.assertEqual(_effective_audio_slot(value), "A")

    def test_export_fps_checks_use_output_grid_without_changing_project_fps(self):
        value = project(4.)
        self.assertIsNotNone(require_layout_coverage(value, {"fps": 60}))
        self.assertEqual(value["settings"]["fps"], 30)
        value["manual"]["source_tracks"]["A"] = []
        with self.assertRaises(LayoutCoverageError):
            require_layout_coverage(value, {"fps": 60})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe unavailable")
    def test_real_render_preserves_duration_audio_caption_and_persists_warning(self):
        def run(args):
            return subprocess.run(args, check=True, capture_output=True, timeout=40).stdout
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(copy.deepcopy(DEFAULTS), root, root, root / "projects", root / "exports", root / "cache", "ffmpeg", "ffprobe")
            for folder in (settings.projects_dir, settings.exports_dir, settings.cache_dir):
                folder.mkdir(parents=True, exist_ok=True)
            store = ProjectStore(settings)
            initial = store.create("Synthetic automatic layout fallback")
            value = {**initial, **project(4.), "id": initial["id"]}
            value["manual"]["text_clips"] = [{"id": "text_"+'a'*32, "kind": "caption", "start": 1., "end": 2.,
                "text": "Preserved caption", "style": "clean", "position": "bottom", "scale": 100}]
            store.save(value)
            project_root = store.project_dir(value["id"])
            (project_root / "media").mkdir(exist_ok=True)
            for slot, color, tone in (("A", "red", 440), ("B", "lime", 880)):
                run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color={color}:s=160x90:r=30:d=4",
                     "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000:duration=4",
                     "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(project_root / value["sources"][slot]["relative_path"])])
            before = store.load(value["id"])
            context = JobContext(Job("synthetic-fallback", "render", value["id"]), threading.Lock())
            with patch("cutroom.render._dimensions", return_value=(160, 90)):
                result = render_project(context, value["id"], store, settings, {"_require_layout_coverage": True, "_force_software": True, "quality": "fast"})
            record = result["export"]
            self.assertAlmostEqual(record["duration"], 4., delta=.04)
            self.assertEqual(record["layout_fallback"]["missing_seconds"], 4.)
            self.assertEqual(record["review"]["checks"][0]["id"], "layout_fallback")
            reopened = store.load(value["id"])
            self.assertEqual(reopened["exports"][0]["layout_fallback"], record["layout_fallback"])
            for key in ("manual", "settings", "sources", "draft"):
                self.assertEqual(reopened[key], before[key])
            output = settings.exports_dir / record["name"]
            whites = []
            for at in (.5, 1.5, 2.5):
                frame = run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(output), "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
                self.assertGreater(frame[(5*160+5)*3], 200)
                self.assertLess(frame[(5*160+5)*3+1], 50)
                whites.append(sum(min(frame[i:i+3]) > 180 for i in range(0, len(frame), 3)))
            self.assertLess(whites[0], 5); self.assertGreater(whites[1], 20); self.assertLess(whites[2], 5)
            samples = array('f', run(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))[48000:52800]
            def level(frequency):
                return 2*abs(sum(v*complex(math.cos(2*math.pi*frequency*i/48000),math.sin(2*math.pi*frequency*i/48000)) for i,v in enumerate(samples)))/len(samples)
            self.assertGreater(level(440), .025); self.assertLess(level(880), .005)
            # A valid B input that is mapped only in the middle keeps its split
            # picture and chosen sound there. B-audio gaps stay silent, not A.
            def partial(current):
                current["manual"]["source_tracks"]["B"] = [{"id": "b", "start": 1., "end": 3., "source_start": 0.}]
                current["manual"]["sequence"]["camera_plan"][0]["camera"] = "side_by_side"
                current["manual"]["source_mixer"].update(audio_slot="B", first_slot="A", default_layout="side_by_side")
            store.update(value["id"], partial)
            with patch("cutroom.render._dimensions", return_value=(160, 90)):
                result = render_project(JobContext(Job("partial", "render", value["id"]), threading.Lock()),
                                        value["id"], store, settings, {"_require_layout_coverage": True, "_force_software": True, "quality": "fast"})
            self.assertEqual(result["export"]["layout_fallback"]["missing_seconds"], 2.)
            output = settings.exports_dir / result["export"]["name"]
            for at, right_color in ((.5, 0), (1.5, 1), (3.5, 0)):
                frame = run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(output), "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
                self.assertGreater(frame[(30*160+120)*3+right_color], 200, (at, list(frame[(30*160+120)*3:(30*160+120)*3+3])))
            audio = array('f', run(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
            for at in (.3, 3.3):
                self.assertLess(max(abs(v) for v in audio[int(at*48000):int(at*48000)+4800]), .005)
            samples = audio[72000:76800]
            self.assertGreater(level(880), .025); self.assertLess(level(440), .005)
            # Legacy synchronized edits obey the same explicit B-audio choice.
            # Offset in either direction yields silence, never unrelated A sound.
            for offset in (-10., 10.):
                def legacy(current):
                    current["manual"].pop("sequence", None)
                    current["manual"].pop("source_tracks", None)
                    current["manual"]["source_mixer"].update(audio_slot="B", sync_offset=offset)
                store.update(value["id"], legacy)
                with patch("cutroom.render._dimensions", return_value=(160, 90)):
                    rendered = render_project(JobContext(Job(f"legacy-{offset}", "render", value["id"]), threading.Lock()),
                                              value["id"], store, settings, {"_require_layout_coverage": True, "_force_software": True, "quality": "fast"})
                self.assertEqual(rendered["export"]["layout_fallback"]["missing_seconds"], 4.)
                output = settings.exports_dir / rendered["export"]["name"]
                silent = array('f', run(["ffmpeg", "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
                self.assertGreater(len(silent), 190000)
                self.assertLess(max(abs(sample) for sample in silent), .005)
            store.update(value["id"], lambda current: current["manual"].update(copy.deepcopy(value["manual"])))
            store.update(value["id"], partial)
            # Missing source files remain real errors; fallback is not an error
            # swallowing mechanism and must not claim another successful export.
            source_b = project_root / value["sources"]["B"]["relative_path"]
            held = source_b.with_suffix('.held'); source_b.rename(held)
            try:
                with self.assertRaises(FileNotFoundError):
                    render_project(JobContext(Job("missing-file", "render", value["id"]), threading.Lock()),
                                   value["id"], store, settings, {"_require_layout_coverage": True})
            finally:
                held.rename(source_b)
            # A stale queue snapshot cannot turn missing A into a permitted fallback.
            store.update(value["id"], lambda current: current["manual"]["source_tracks"].update(A=[]))
            with self.assertRaises(LayoutCoverageError):
                render_project(JobContext(Job("changed", "render", value["id"]), threading.Lock()), value["id"], store, settings, {"_require_layout_coverage": True})
            self.assertEqual(len(store.load(value["id"])["exports"]), 4)


if __name__ == "__main__":
    unittest.main()
