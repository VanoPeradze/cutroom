import json

import pytest

from cutroom.jobs import Job


def test_failed_job_hides_internal_diagnostics_without_mutating_them():
    diagnostics = {
        "traceback": 'Traceback: File "C:/private-user/private-project/worker.py", line 9',
        "internal_context": "synthetic-private-context",
    }
    job = Job("job_failed", "analysis", "project_test", status="failed",
              progress=0.4, message="Failed", error="The model is unavailable. Retry setup.",
              result=diagnostics)

    public = job.public()

    assert public["result"] is None
    assert public["error"] == "The model is unavailable. Retry setup."
    assert public["status"] == "failed" and public["progress"] == 0.4
    assert "traceback" not in json.dumps(public)
    assert "private-user" not in json.dumps(public)
    assert "synthetic-private-context" not in json.dumps(public)
    assert job.result is diagnostics


@pytest.mark.parametrize("status", ["completed", "running", "queued", "cancelled", "interrupted"])
def test_nonfailed_job_results_and_progress_remain_available(status):
    result = {"draft_id": "draft_test", "segments": ["segment_1"]}
    job = Job("job_result", "analysis", "project_test", status=status,
              progress=0.75, message="Prepared draft", result=result)

    public = job.public()

    assert public["result"] == result
    assert public["progress"] == 0.75
    assert public["message"] == "Prepared draft"
