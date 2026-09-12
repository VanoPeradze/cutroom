from __future__ import annotations

import threading
import time

from cutroom.jobs import JobManager


def test_background_job_does_not_starve_foreground_job():
    manager = JobManager(workers=1, background_workers=1)
    release = threading.Event()

    def background(context):
        context.update(0.1, "background")
        release.wait(timeout=2)
        return "background-done"

    def foreground(context):
        context.update(0.5, "foreground")
        return "foreground-done"

    bg = manager.submit("prepare_source", "p1", background)
    time.sleep(0.05)
    fg = manager.submit("director", "p1", foreground)

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and manager.get(fg.id).status not in {"completed", "failed"}:
        time.sleep(0.01)

    assert manager.get(fg.id).status == "completed"
    assert manager.get(bg.id).status == "running"
    release.set()


def test_model_install_uses_background_pool():
    manager = JobManager(workers=1, background_workers=1)
    assert "model_install" in manager.BACKGROUND_KINDS
    assert "prepare_source" in manager.BACKGROUND_KINDS
    assert "director" not in manager.BACKGROUND_KINDS
