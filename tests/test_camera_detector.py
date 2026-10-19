from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import vision


def test_installed_camera_detector_has_real_xml_and_can_run():
    # This must fail, rather than skip, for an installed but incompatible cv2.
    # Merely importing cv2 hid the missing detector API in OpenCV 5.
    import cv2

    result = vision.check_camera_detector_capability()

    assert result["available"] is True
    assert result["opencv_version"] == cv2.__version__
    assert result["classifier_count"] == 3
    assert result["smoke_check"] == "detectMultiScale_blank_frame"
    assert set(result["cascade_files"]) == {
        "haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_alt2.xml",
        "haarcascade_profileface.xml",
    }
    for filename in result["cascade_files"]:
        assert (Path(cv2.data.haarcascades) / filename).is_file()


def test_real_analyzer_distinguishes_blank_video_from_unavailable_detector(tmp_path):
    import cv2
    import numpy as np

    path = tmp_path / "blank.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 90))
    try:
        assert writer.isOpened(), "OpenCV must be able to write the tiny smoke video"
        for _ in range(10):
            writer.write(np.zeros((90, 160, 3), dtype=np.uint8))
    finally:
        writer.release()
    assert path.is_file() and path.stat().st_size > 0
    progress = []

    result = vision.analyze_faces_and_embedded_camera(
        path, 1.0, samples=10, progress=lambda value, message: progress.append(value),
    )

    assert result["available"] is True, result
    assert result["reason"] == "no_stable_face"
    assert result["faces"] == []
    assert result["embedded_camera"] is None
    assert result["focus_safe"] is False
    # Codec seeking can round the final half-frame timestamp past the last frame.
    # Require genuine decoded samples without assuming that boundary is readable.
    assert len(progress) >= 8
    assert result["decoded_samples"] == len(progress)
    # The capture is closed after analysis, including on Windows.
    path.unlink()


@pytest.mark.parametrize(
    ("failure", "warning"),
    [
        ("missing_api", "CascadeClassifier"),
        ("noncallable_api", "CascadeClassifier"),
        ("missing_directory", "Haar cascade directory"),
        ("missing_xml", "haarcascade_profileface.xml is missing"),
        ("empty_classifier", "the classifier is empty"),
        ("broken_inference", "smoke inference failed"),
    ],
)
def test_incompatible_camera_detector_fails_before_opening_video(
    tmp_path, monkeypatch, failure, warning,
):
    for filename in vision._CAMERA_CASCADE_FILES:
        (tmp_path / filename).write_text("fake classifier for failure-path testing", encoding="utf-8")

    class Classifier:
        def __init__(self, path):
            self.path = Path(path)

        def empty(self):
            return failure == "empty_classifier"

        def detectMultiScale(self, _frame, **_kwargs):
            if failure == "broken_inference":
                raise RuntimeError("smoke inference failed")
            return []

    def unexpected_capture(_path):
        pytest.fail("A broken detector must be rejected before opening the video")

    fake_cv2 = SimpleNamespace(
        CascadeClassifier=Classifier,
        data=SimpleNamespace(haarcascades=str(tmp_path)),
        VideoCapture=unexpected_capture,
    )
    if failure == "missing_api":
        del fake_cv2.CascadeClassifier
    elif failure == "noncallable_api":
        fake_cv2.CascadeClassifier = None
    elif failure == "missing_directory":
        del fake_cv2.data
    elif failure == "missing_xml":
        (tmp_path / "haarcascade_profileface.xml").unlink()
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    result = vision.analyze_faces_and_embedded_camera(tmp_path / "unused.avi", 1.0)

    assert result["available"] is False
    assert result["reason"] == "opencv_detector_unavailable"
    assert warning in result["warning"]
    assert "Run CUTROOM setup again" in result["warning"]
    assert result["faces"] == []
    assert result["embedded_camera"] is None
    assert result["focus_safe"] is False


@pytest.mark.parametrize("failure", ["open", "metadata", "read", "cancel", "decode"])
def test_camera_capture_is_released_on_all_early_exits(tmp_path, monkeypatch, failure):
    released = []

    class Capture:
        def isOpened(self):
            return failure != "open"

        def get(self, _property):
            if failure == "metadata":
                raise RuntimeError("metadata failed")
            return 160

        def set(self, *_args):
            pass

        def read(self):
            if failure == "decode":
                return False, None
            raise RuntimeError("read failed")

        def release(self):
            released.append(True)

    fake_cv2 = SimpleNamespace(
        VideoCapture=lambda _path: Capture(),
        CAP_PROP_FRAME_WIDTH=1,
        CAP_PROP_FRAME_HEIGHT=2,
        CAP_PROP_POS_MSEC=3,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(vision, "_load_camera_classifiers", lambda _cv2: [object()] * 3)
    cancellation_checks = []

    def cancel_check():
        cancellation_checks.append(True)
        if failure == "cancel" and len(cancellation_checks) > 1:
            raise RuntimeError("cancelled")

    if failure == "open":
        result = vision.analyze_faces_and_embedded_camera(tmp_path / "unused.avi", 1.0)
        assert result["available"] is False
        assert result["reason"] == "video_open_failed"
    elif failure == "decode":
        result = vision.analyze_faces_and_embedded_camera(tmp_path / "unused.avi", 1.0)
        assert result["available"] is False
        assert result["reason"] == "video_decode_failed"
        assert result["decoded_samples"] == 0
        assert "No video frames could be decoded" in result["warning"]
        assert result["embedded_camera"] is None
    else:
        message = {"metadata": "metadata failed", "read": "read failed", "cancel": "cancelled"}[failure]
        with pytest.raises(RuntimeError, match=message):
            vision.analyze_faces_and_embedded_camera(
                tmp_path / "unused.avi", 1.0, cancel_check=cancel_check,
            )
    assert released == [True]


def test_analyzer_reuses_the_three_smoke_checked_classifiers(tmp_path, monkeypatch):
    import numpy as np

    for filename in vision._CAMERA_CASCADE_FILES:
        (tmp_path / filename).write_text("fake classifier for reuse testing", encoding="utf-8")
    loads = []
    calls = []

    class Classifier:
        def __init__(self, path):
            self.filename = Path(path).name
            loads.append(self.filename)

        def empty(self):
            return False

        def detectMultiScale(self, frame, **_kwargs):
            calls.append((self.filename, frame.shape))
            return []

    class Capture:
        def isOpened(self):
            return True

        def get(self, property):
            return 160 if property == 1 else 90

        def set(self, *_args):
            pass

        def read(self):
            return True, np.zeros((90, 160, 3), dtype=np.uint8)

        def release(self):
            pass

    fake_cv2 = SimpleNamespace(
        CascadeClassifier=Classifier,
        data=SimpleNamespace(haarcascades=str(tmp_path)),
        VideoCapture=lambda _path: Capture(),
        CAP_PROP_FRAME_WIDTH=1,
        CAP_PROP_FRAME_HEIGHT=2,
        CAP_PROP_POS_MSEC=3,
        COLOR_BGR2GRAY=4,
        cvtColor=lambda frame, _conversion: frame[:, :, 0],
        equalizeHist=lambda frame: frame,
        flip=lambda frame, _direction: np.fliplr(frame),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    result = vision.analyze_faces_and_embedded_camera(tmp_path / "unused.avi", 1.0, samples=10)

    assert result["available"] is True
    assert result["decoded_samples"] == 10
    assert loads == list(vision._CAMERA_CASCADE_FILES)
    assert len([shape for _name, shape in calls if shape == (64, 64)]) == 3
    assert len([shape for _name, shape in calls if shape == (90, 160)]) == 40
