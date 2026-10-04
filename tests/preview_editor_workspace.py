"""Isolated, synthetic UI fixture. Run manually; never changes real projects."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cutroom.config import load_settings
from cutroom.media import probe_media
from server import create_app


def main():
    with tempfile.TemporaryDirectory(prefix="cutroom-ui-preview-") as work:
        os.environ["CUTROOM_DATA_DIR"] = str(Path(work) / "data")
        settings = load_settings()
        settings.raw["ai"]["enabled"] = False
        app = create_app(settings)
        if "--header-progress" in sys.argv:
            @app.get("/test-header-progress.js")
            def header_progress_script():
                from flask import Response
                return Response("""
                    document.addEventListener('DOMContentLoaded', () => {
                      const button = document.createElement('button');
                      button.id = 'testHeaderProgress';
                      button.textContent = 'Simulate progress';
                      button.className = 'button compact';
                      document.querySelector('.top-actions').append(button);
                      button.addEventListener('click', () => {
                        const bar = document.getElementById('activeJobBar');
                        bar.hidden = !bar.hidden;
                        document.getElementById('activeJobDetail').textContent = 'Test-only progress: preparing a long recording with two sources, captions and audio. No AI calls.';
                      });
                    });
                    """, mimetype="application/javascript")

            @app.after_request
            def inject_header_progress_fixture(response):
                if response.mimetype == "text/html":
                    response.direct_passthrough = False
                    response.set_data(response.get_data().replace(
                        b"</head>", b'<script src="/test-header-progress.js"></script></head>'
                    ))
                return response
        if "--audio-graph-conflict" in sys.argv:
            @app.get("/test-audio-graph-conflict.js")
            def audio_graph_conflict_script():
                from flask import Response
                # Test-only; the real app never exposes this route.
                return Response("""
                    const audioFactory = AudioContext.prototype.createMediaElementSource;
                    let injectedAudioConflict = false;
                    AudioContext.prototype.createMediaElementSource = function(element) {
                      if (!injectedAudioConflict) {
                        injectedAudioConflict = true;
                        audioFactory.call(this, element);
                        document.documentElement.dataset.audioConflict = 'injected';
                      }
                      return audioFactory.call(this, element);
                    };
                    """, mimetype="application/javascript")

            @app.after_request
            def simulate_audio_graph_conflict(response):
                if response.mimetype == "text/html":
                    response.direct_passthrough = False
                    response.set_data(response.get_data().replace(
                        b"</head>", b'<script src="/test-audio-graph-conflict.js"></script></head>'
                    ))
                return response
        store = app.extensions["cutroom_store"]
        project = store.create("UI sample · synthetic footage")
        target = store.project_dir(project["id"]) / "media" / "source-A.mp4"
        subprocess.run([
            shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=12",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(target),
        ], check=True)
        project["sources"]["A"] = {
            "slot": "A", "name": "Synthetic sample.mp4", "relative_path": "media/source-A.mp4",
            "preparation": "ready", **probe_media(target, settings),
        }
        if "--two-sources" in sys.argv:
            target_b = target.with_name("source-B.mp4")
            shutil.copy2(target, target_b)
            project["sources"]["B"] = {
                **project["sources"]["A"], "slot": "B", "name": "Synthetic camera.mp4",
                "relative_path": "media/source-B.mp4",
            }
        keeps = [{"start": 0, "end": 4}, {"start": 6, "end": 12}]
        project["analysis"] = {"transcript": {"language": "en", "language_probability": 1,
            "segments": [{"id": "s1", "start": 0, "end": 4, "text": "Sample captions for interface testing", "words": []}]},
            "audio": {}, "vision": {}, "sync": None}
        if "--transcript" in sys.argv:
            project["analysis"]["transcript"]["segments"] = [
                {"id": f"s{index}", "start": index, "end": index + 1, "words": [],
                 "text": ("זה טקסט לדוגמה בעברית כדי לבדוק את תיקון הכתוביות בנוחות ובצורה ברורה." if index % 2
                          else "This is a longer sample transcript line. It needs space to read, review and correct without losing context.")}
                for index in range(12)
            ]
        project["draft"] = {"title": "Your first cut", "summary": "Synthetic UI test. No AI analysis was run.",
            "goal": "short", "aspect": "9:16", "source_duration": 12, "output_duration": 10,
            "keep_ranges": keeps, "cuts": [{"start": 4, "end": 6}],
            "camera_plan": [{**item, "camera": "A"} for item in keeps], "decisions": []}
        if "--gaps" in sys.argv:
            from cutroom.editing import apply_manual_edit
            for slot in project["sources"]:
                apply_manual_edit(project, {"action":"sequence_remove_range", "slot":slot, "start":2, "end":4})
        if "--embedded" in sys.argv:
            project.setdefault("manual", {})["embedded_camera"] = {
                "x": .7, "y": .05, "w": .25, "h": .3,
                "content_focus": {"x": .5, "y": .5},
            }
            project["settings"]["layout"] = "embedded_stack"
            project["draft"].update({
                "layout": "embedded_stack", "embedded_layout_confirmed": True,
                "camera_plan": [{**item, "camera": "embedded_stack"} for item in keeps],
            })
        if "--onboarding" in sys.argv:
            project["draft"] = None
            project["analysis"] = None
            project["settings"].update(workflow="manual", goal="youtube", aspect="16:9")
        store.save(project)
        try:
            app.run(host="127.0.0.1", port=8766, debug=False, use_reloader=False)
        finally:
            app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


if __name__ == "__main__":
    main()
