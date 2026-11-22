import shutil
import subprocess

import pytest

from cutroom.grading import (
    GradingError, color_filter, keyframe_transform_filter, lut_path, normalize_color, normalize_keyframes,
    parse_cube, save_lut,
)
from cutroom.render import transform_filter


def identity_cube(size=2):
    rows = [f"{r / (size - 1):.3f} {g / (size - 1):.3f} {b / (size - 1):.3f}"
            for b in range(size) for g in range(size) for r in range(size)]
    return "TITLE \"identity\"\n# comment\nLUT_3D_SIZE %d\n" % size + "\n".join(rows) + "\n"


def test_neutral_grade_compiles_to_nothing_and_values_are_clamped():
    assert color_filter({}) is None
    clean = normalize_color({"look": "bogus", "exposure": 9, "saturation": float("nan")})
    assert clean["look"] == "none" and clean["exposure"] == 1.0 and clean["saturation"] == 0.0
    with pytest.raises(GradingError):
        normalize_color({"look": "warm", "exposure": 2}, strict=True)
    with pytest.raises(GradingError):
        normalize_color({"filter": "eq=1"}, strict=True)


def test_grade_chain_uses_only_whitelisted_filters():
    chain = color_filter({"look": "teal_orange", "exposure": 0.2, "contrast": -0.4, "saturation": 0.5, "temperature": 0.5})
    assert chain.startswith("colorbalance=")
    assert "eq=brightness=0.0300:contrast=0.8000:saturation=1.5000" in chain
    assert chain.endswith("colortemperature=temperature=5500.0")


def test_cube_is_validated_and_stored_by_content(tmp_path):
    with pytest.raises(GradingError):
        parse_cube("LUT_1D_SIZE 4\n0 0 0\n")
    with pytest.raises(GradingError):
        parse_cube("LUT_3D_SIZE 2\n0 0 0\n")
    lut_id = save_lut(tmp_path, identity_cube())
    assert save_lut(tmp_path, identity_cube()) == lut_id
    color = normalize_color({"lut_id": lut_id, "lut_name": "Film"}, strict=True)
    path = lut_path(tmp_path, color)
    assert path is not None and path.parent.name == "luts"
    assert "lut3d=file='" in color_filter(color, path)
    assert lut_path(tmp_path, normalize_color({"lut_id": "0" * 16})) is None
    with pytest.raises(GradingError):
        normalize_color({"lut_id": "../../x"}, strict=True)


def test_keyframes_are_sorted_deduplicated_and_bounded():
    rows = normalize_keyframes([{"time": 4, "zoom": 1.5}, {"time": 1, "zoom": 9, "x": 2}, {"time": 4, "zoom": 1.2}])
    assert rows == [{"time": 1.0, "zoom": 3.0, "x": 1.0, "y": 0.5}, {"time": 4.0, "zoom": 1.2, "x": 0.5, "y": 0.5}]
    with pytest.raises(GradingError):
        normalize_keyframes([{"zoom": 2}], strict=True)
    assert keyframe_transform_filter([{"time": 0, "zoom": 1}], 320, 180) is None


def test_render_prefers_keyframes_and_folds_in_punch_ins():
    project = {"settings": {}, "draft": {"goal": "youtube", "punch_ins": [{"start": 1, "end": 2}]},
               "manual": {"keyframes": [{"time": 0, "zoom": 1}, {"time": 2, "zoom": 2, "x": 0.25}]}}
    expression = transform_filter(project, 320, 180, 30, 5)
    assert expression.startswith("scale=") and "between(t,1.000,2.000)" in expression
    project["manual"]["keyframes"] = []
    assert transform_filter(project, 320, 180, 30, 5).startswith("zoompan=")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_ffmpeg_runs_grade_lut_and_keyframes(tmp_path):
    project_dir = tmp_path / "project: one"  # a colon must survive filter escaping
    lut = lut_path(project_dir, normalize_color({"lut_id": save_lut(project_dir, identity_cube(3))}))
    grade = color_filter({"look": "vintage", "exposure": 0.3, "temperature": -0.4, "lut_id": lut.stem}, lut)
    motion = keyframe_transform_filter([{"time": 0, "zoom": 1}, {"time": 2, "zoom": 2, "x": 0.8, "y": 0.2}], 320, 180)
    output = tmp_path / "out.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=2",
                    "-filter_complex", f"[0:v]{motion},{grade}[o]", "-map", "[o]", str(output)], check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,nb_frames", "-of", "csv=p=0",
                            str(output)], check=True, capture_output=True, text=True).stdout.strip()
    assert probe == "320,180,60"


def test_api_uploads_a_lut_and_saves_the_grade(tmp_path, monkeypatch):
    from cutroom.config import load_settings
    from server import create_app

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = create_app(settings)
    app.config.update(TESTING=True)
    client = app.test_client()
    project = client.post("/api/projects", json={"name": "Grade"}).get_json()["project"]
    base = f"/api/projects/{project['id']}"
    assert client.post(f"{base}/luts", data="LUT_3D_SIZE 2\n", content_type="text/plain").status_code == 400
    assert client.post(f"{base}/luts", json={"text": identity_cube()}).status_code == 415
    uploaded = client.post(f"{base}/luts?name=Film", data=identity_cube(17), content_type="text/plain")
    assert uploaded.status_code == 200
    lut = uploaded.get_json()["lut"]
    color = {"look": "warm", "exposure": 0.1, "contrast": 0, "saturation": 0.2, "temperature": 0,
             "lut_id": lut["id"], "lut_name": lut["name"]}
    saved = client.patch(base, json={"manual": {"color": color, "keyframes": [{"time": 1, "zoom": 1.4, "x": 0.3, "y": 0.5}]}})
    assert saved.status_code == 200
    assert saved.get_json()["project"]["manual"]["color"]["lut_id"] == lut["id"]
    assert client.patch(base, json={"manual": {"color": {"look": "neon"}}}).status_code == 400
    assert client.patch(base, json={"manual": {"keyframes": [{"time": 1, "zoom": 5}]}}).status_code == 400
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)
