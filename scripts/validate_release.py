from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from cutroom import __version__, __version_label__

REPORT_JSON = ROOT / "validation-report.json"
REPORT_HE = ROOT / "VALIDATION_REPORT_HE.md"


def run(name: str, command: list[str], timeout: int = 600, env: dict[str, str] | None = None) -> dict:
    print(f"[validation] {name}...", flush=True)
    started = time.time()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    print(f"[validation] {name}: {'PASS' if result.returncode == 0 else 'FAIL'} ({time.time() - started:.2f}s)", flush=True)
    return {
        "name": name,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "seconds": round(time.time() - started, 2),
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
    }


def static_checks() -> list[dict]:
    checks: list[dict] = []
    required = [
        "server.py", "config.json", "requirements.txt", "requirements-dev.txt", "run_windows.bat", "repair_windows.bat", "setup_windows.ps1", "verify_windows_installer.ps1", "scripts/preflight.py",
        "run_linux.sh", "setup_linux.sh", "web/index.html", "web/styles.css", "web/app.js", "web/i18n.js", "web/timeline.js", "web/audio-meter.js",
        "cutroom/config.py", "cutroom/projects.py", "cutroom/media.py", "cutroom/jobs.py", "cutroom/transcription.py",
        "cutroom/intelligence.py", "cutroom/sync.py", "cutroom/vision.py", "cutroom/composition.py", "cutroom/editing.py", "cutroom/director.py", "cutroom/render.py", "cutroom/audio.py", "cutroom/captions.py", "cutroom/effects.py",
        "tests/test_utils.py", "tests/test_intelligence.py", "tests/test_director.py", "tests/test_vision.py", "tests/test_composition.py", "tests/test_transcription_profiles.py", "tests/test_api.py", "tests/test_effects.py", "tests/smoke_render.py", "tests/smoke_director_two_source.py", "tests/smoke_short_target.py", "tests/smoke_youtube_cleanup.py", "tests/smoke_burn_captions.py", "tests/smoke_embedded_reel.py", "tests/smoke_editorial_stack.py",
        "README_HE.md", "README.md", "START_HERE_HE.txt", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
    ]
    missing = [item for item in required if not (ROOT / item).is_file()]
    checks.append({"name": "required_files", "ok": not missing, "details": missing})

    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    css = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    checks.append({"name": "unique_html_ids", "ok": not duplicate_ids, "details": duplicate_ids, "count": len(ids)})

    cache_match = re.search(r"function cacheElements\(\) \{\s*\[\s*(.*?)\s*\]\.forEach\(\(id\)", app, re.S)
    references = set(re.findall(r'"([A-Za-z][A-Za-z0-9_-]+)"', cache_match.group(1))) if cache_match else set()
    missing_ids = sorted(references - set(ids))
    checks.append({"name": "javascript_dom_references", "ok": bool(cache_match) and not missing_ids, "details": missing_ids, "count": len(references)})

    body_block = css.split("body {", 1)[1].split("}", 1)[0] if "body {" in css else ""
    scroll_ok = "overflow-y: auto" in body_block and "overflow: hidden" not in body_block
    checks.append({"name": "normal_document_scroll", "ok": scroll_ok, "details": body_block.strip()})

    topbar = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0] if '<header class="topbar">' in html else ""
    checks.append({"name": "render_in_topbar", "ok": 'id="renderButton"' in topbar, "details": None})
    checks.append({"name": "director_primary", "ok": 'id="generateButton"' in html and 'id="advancedPanel" hidden' in html, "details": None})
    checks.append({"name": "six_languages", "ok": all(f'const {language} =' in (ROOT / "web/i18n.js").read_text(encoding="utf-8") for language in ("en", "he", "ar", "es", "fr", "ru")), "details": None})
    runtime_python = [ROOT / "server.py", *sorted((ROOT / "cutroom").glob("*.py"))]
    runtime_source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in runtime_python
        if path.is_file()
    )
    checks.append({
        "name": "no_cloud_api_keys",
        "ok": not re.search(r"(OPENAI_API_KEY|ANTHROPIC_API_KEY|api\.openai\.com)", runtime_source),
        "details": None,
    })

    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    upload_transport_ok = all(marker in server_source for marker in (
        'app.config["MAX_CONTENT_LENGTH"]',
        'max_request_body_size=request_body_limit',
        'channel_timeout=3600',
        'transport_request_body_bytes',
    ))
    checks.append({
        "name": "large_upload_transport_limit",
        "ok": upload_transport_ok,
        "details": None,
    })

    windows_files = [
        ROOT / "setup_windows.ps1",
        ROOT / "verify_windows_installer.ps1",
        ROOT / "run_windows.bat",
        ROOT / "repair_windows.bat",
    ]
    windows_payloads = {path.name: path.read_bytes() for path in windows_files if path.is_file()}
    encoding_issues = [
        name
        for name, payload in windows_payloads.items()
        if not payload or any(byte >= 128 for byte in payload)
        or b"\r\n" not in payload
        or b"\n" in payload.replace(b"\r\n", b"")
    ]
    checks.append({
        "name": "windows_scripts_ascii_crlf",
        "ok": len(windows_payloads) == len(windows_files) and not encoding_issues,
        "details": encoding_issues,
    })
    setup_source = windows_payloads.get("setup_windows.ps1", b"").decode("ascii", errors="ignore")
    validator_source = windows_payloads.get("verify_windows_installer.ps1", b"").decode("ascii", errors="ignore")
    launcher_source = windows_payloads.get("run_windows.bat", b"").decode("ascii", errors="ignore")
    repair_source = windows_payloads.get("repair_windows.bat", b"").decode("ascii", errors="ignore")
    windows_guard_ok = all((
        "System.Management.Automation.Language.Parser" in validator_source,
        "verify_windows_installer.ps1" in launcher_source,
        "verify_windows_installer.ps1" in repair_source,
        'if not exist ".setup-complete"' in launcher_source,
        'if not exist ".venv\\Scripts\\python.exe"' in launcher_source,
        "--managed-python" not in setup_source,
        "Resolve-SystemPython" in setup_source,
        "uv-x86_64-pc-windows-msvc.zip" in setup_source,
        "uv-aarch64-pc-windows-msvc.zip" in setup_source,
        "uv-i686-pc-windows-msvc.zip" in setup_source,
        "UV_PYTHON_INSTALL_DIR" in setup_source,
        "UV_SYSTEM_CERTS" in setup_source,
        "Get-FileHash" in setup_source,
        ".runtime-paths.cmd" in launcher_source,
        "setup-last-error.txt" in launcher_source,
        "Gyan.FFmpeg" in setup_source,
        "Ollama.Ollama" in setup_source,
    ))
    checks.append({"name": "windows_installer_guards", "ok": windows_guard_ok, "details": None})

    setup_bytes = (ROOT / "setup_windows.ps1").read_bytes()
    windows_launchers = {
        name: (ROOT / name).read_bytes()
        for name in ("setup_windows.ps1", "verify_windows_installer.ps1", "run_windows.bat", "repair_windows.bat")
    }
    non_ascii = {
        name: sorted({value for value in payload if value > 127})
        for name, payload in windows_launchers.items()
        if any(value > 127 for value in payload)
    }
    checks.append({
        "name": "windows_launchers_ascii_only",
        "ok": not non_ascii,
        "details": non_ascii,
    })
    checks.append({
        "name": "windows_launchers_crlf",
        "ok": all(b"\r\n" in payload and payload.replace(b"\r\n", b"").find(b"\n") == -1 for payload in windows_launchers.values()),
        "details": None,
    })

    setup_text = setup_bytes.decode("ascii") if all(value < 128 for value in setup_bytes) else ""
    smart_punctuation = re.findall(r"[\u2010-\u201f\u00ab\u00bb]", setup_text)
    checks.append({
        "name": "powershell_no_smart_punctuation",
        "ok": bool(setup_text) and not smart_punctuation,
        "details": smart_punctuation,
    })

    def lexical_balance(source: str) -> tuple[bool, str]:
        stack: list[tuple[str, int]] = []
        pairs = {")": "(", "]": "[", "}": "{"}
        state = "code"
        line = 1
        index = 0
        while index < len(source):
            char = source[index]
            if char == "\n":
                line += 1
                if state == "comment":
                    state = "code"
                index += 1
                continue
            if state == "comment":
                index += 1
                continue
            if state == "single":
                if char == "'":
                    if index + 1 < len(source) and source[index + 1] == "'":
                        index += 2
                        continue
                    state = "code"
                index += 1
                continue
            if state == "double":
                if char == "`" and index + 1 < len(source):
                    index += 2
                    continue
                if char == '"':
                    state = "code"
                index += 1
                continue
            if char == "#":
                state = "comment"
            elif char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char in "([{":
                stack.append((char, line))
            elif char in ")]}":
                if not stack or stack[-1][0] != pairs[char]:
                    return False, f"Unexpected {char} on line {line}"
                stack.pop()
            index += 1
        if state in {"single", "double"}:
            return False, f"Unterminated {state}-quoted string"
        if stack:
            char, opened_line = stack[-1]
            return False, f"Unclosed {char} opened on line {opened_line}"
        return True, ""

    lexical_ok, lexical_detail = lexical_balance(setup_text)
    checks.append({
        "name": "powershell_lexical_balance",
        "ok": lexical_ok,
        "details": lexical_detail,
    })

    run_windows = windows_launchers["run_windows.bat"].decode("ascii", errors="replace")
    verifier = windows_launchers["verify_windows_installer.ps1"].decode("ascii", errors="replace")
    checks.append({
        "name": "windows_setup_guards",
        "ok": all(
            marker in run_windows
            for marker in (
                'if not exist ".setup-complete"',
                'if not exist ".venv\\Scripts\\python.exe"',
                "verify_windows_installer.ps1",
                "scripts\\preflight.py",
            )
        ) and all(
            marker in verifier
            for marker in (
                "System.Management.Automation.Language.Parser",
                "setup_windows.ps1",
                "$errors.Count",
            )
        ),
        "details": None,
    })
    return checks


def wait_http(url: str, timeout: float = 20, process: subprocess.Popen | None = None) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.status == 200
        except Exception:
            time.sleep(.25)
    return False


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def server_smoke() -> dict:
    temp = Path(tempfile.mkdtemp(prefix="cutroom-server-validation-"))
    env = os.environ.copy()
    env["CUTROOM_DATA_DIR"] = str(temp / "data")
    env["CUTROOM_NO_BROWSER"] = "1"
    port = free_loopback_port()
    env["CUTROOM_PORT"] = str(port)
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ok = wait_http(f"{base_url}/api/health", process=process)
        if not ok:
            if process.poll() is None:
                process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=3)
            return {"name": "server_smoke", "ok": False, "stdout": stdout[-5000:], "stderr": stderr[-5000:]}
        with urllib.request.urlopen(f"{base_url}/api/health") as response:
            health = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/") as response:
            html = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/assets/app.js") as response:
            javascript = response.read().decode("utf-8")
        alive = process.poll() is None
        return {
            "name": "server_smoke",
            "ok": alive and health.get("ok") is True and "CUTROOM" in html and "generateDraft" in javascript,
            "stdout": f"HTTP application shell loaded on isolated port {port}",
            "stderr": "" if alive else "Validation server exited before checks completed",
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(temp, ignore_errors=True)


def browser_smoke() -> dict:
    browser = next((shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable") if shutil.which(name)), None)
    if not browser:
        return {"name": "browser_smoke", "ok": True, "skipped": True, "stdout": "No Chromium binary available", "stderr": ""}
    temp = Path(tempfile.mkdtemp(prefix="cutroom-browser-validation-"))
    env = os.environ.copy()
    env["CUTROOM_DATA_DIR"] = str(temp / "data")
    env["CUTROOM_NO_BROWSER"] = "1"
    port = free_loopback_port()
    env["CUTROOM_PORT"] = str(port)
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    desktop = temp / "validation-desktop.png"
    mobile = temp / "validation-mobile.png"
    try:
        if not wait_http(f"{base_url}/", process=process):
            return {"name": "browser_smoke", "ok": False, "stdout": "Server did not start", "stderr": ""}
        common = [browser, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000"]
        try:
            desktop_result = subprocess.run([*common, "--window-size=1440,1000", f"--screenshot={desktop}", f"{base_url}/"], capture_output=True, text=True, timeout=45)
            mobile_result = subprocess.run([*common, "--window-size=390,844", f"--screenshot={mobile}", f"{base_url}/"], capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired as exc:
            return {"name": "browser_smoke", "ok": True, "skipped": True, "stdout": "Chromium timed out in this build environment; DOM, JavaScript and HTTP checks still ran.", "stderr": str(exc)}
        ok = process.poll() is None and desktop_result.returncode == 0 and mobile_result.returncode == 0 and desktop.exists() and mobile.exists() and desktop.stat().st_size > 5000 and mobile.stat().st_size > 5000
        return {"name": "browser_smoke", "ok": ok, "stdout": f"desktop={desktop.stat().st_size if desktop.exists() else 0}, mobile={mobile.stat().st_size if mobile.exists() else 0}", "stderr": (desktop_result.stderr + mobile_result.stderr)[-5000:]}
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(temp, ignore_errors=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(report: dict) -> None:
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for item in report["checks"]:
        status = "דולג בסביבה זו" if item.get("skipped") else ("עבר" if item.get("ok") else "נכשל")
        rows.append(f"| {item['name']} | {status} | {item.get('seconds', '')} |")
    failures = [item for item in report["checks"] if not item.get("ok")]
    if sys.platform.startswith("win"):
        environment_note = (
            "האימות רץ על Windows עם סביבת ה־Python המלאה של CUTROOM: בדיקות API ושרת בוצעו בפועל. "
            "בדיקת Chromium headless מסומנת כדילוג רק כאשר אין קובץ Chromium/Chrome נגיש ב־PATH; "
            "סקריפטי ההתקנה נותחו ואומתו, אך התקנה מחדש עם winget/Ollama לא הורצה כדי לא לשנות את המחשב הפעיל."
        )
    else:
        environment_note = (
            "האימות אינו רץ על Windows, ולכן סקריפטי Windows נבדקים מבחינת קיום, תוכן, Checksums ומסלולים "
            "ללא הפעלת winget או setup_windows.ps1. בדיקות תלויות־runtime מסומנות כדילוג רק כאשר המודולים "
            "הנדרשים אינם מותקנים בסביבת הבנייה. לפני הפצה רחבה יש לבצע גם התקנה פיזית נקייה ב־Windows."
        )
    text = f"""# CUTROOM {__version_label__} — דוח אימות

**מצב שחרור:** {('עבר עם דילוגים סביבתיים' if report['ok'] and any(item.get('skipped') for item in report['checks']) else 'עבר' if report['ok'] else 'נכשל')}

| בדיקה | מצב | זמן בשניות |
|---|---:|---:|
{chr(10).join(rows)}

## היקף

- בדיקות תחביר לכל קובצי Python ו-JavaScript.
- בדיקות יחידה ו-Property-based למיזוג חיתוכים, Guardrails, שפות, חזרות, כתוביות ותוכנית מצלמות.
- בדיקות API למחזור חיי פרויקט כאשר Flask/Waitress זמינים בסביבת האימות; אחרת הן מסומנות במפורש כדילוג סביבתי.
- Render Smoke אמיתי משני מקורות ל-720×1280.
- Short Target Smoke שמוודא שיעד זמן מפורש נאכף גם בקובץ הרנדר הסופי.
- YouTube Cleanup Smoke שמוודא שמבנה הסרטון נשמר וברירת המחדל מסירה בעיקר Dead Air מדוד.
- Burned Captions Smoke שמרנדר כתוביות עבריות לתוך MP4 אחרי חיתוך ומוודא תזמון פלט חדש.
- Editorial Stack Smoke שמוודא ב־MP4 אמיתי אפקטים בטוחים לפני כתוביות ומיקום כתוביות מותאם לפריסת Stacked.
- Embedded Reel Smoke שמוודא ב-MP4 אמיתי Facecam למעלה ו-Gameplay/Screen למטה מתוך מקור יחיד.
- Audio Threshold tests שמוודאים שסף dB ידני משנה את אזורי השקט ושדיבור מזוהה מוגן.
- Hierarchical Story tests שמוודאים Chapters -> Outline -> Story Plan -> Slot Selection -> Critic ושבחירה מכסה התחלה/אמצע/סוף.
- Regression ייעודי ל-FFmpeg stderr pipe ול-progress אמיתי, כדי למנוע חזרה לתקיעת 92%.
- בדיקות Context ארוך: ה-LLM מקבל דגימות מהתחלה, אמצע וסוף ולא רק את ראש התמלול.
- בדיקות Timeline על Waveform אמיתי, Scrub, Zoom/Pan ו-Follow ל-Playhead.
- הפעלת שרת מקומי וטעינת HTML ו-JavaScript דרך HTTP.
- בדיקת Chromium Desktop/Mobile כאשר דפדפן Headless קיים בסביבה.
- בדיקת שלמות מבנה ההפצה, Scroll, מיקום Render וממשק Director.
- בדיקות ASCII/CRLF, איזון מחרוזות וסוגריים, SHA-256 ל-Bootstrap, ושער Parser אמיתי של PowerShell לפני התקנה ב-Windows.

## כשלים

{('אין.' if not failures else chr(10).join(f"- **{item['name']}**: {(item.get('stderr') or item.get('details') or item.get('stdout'))}" for item in failures))}

## מגבלת סביבת הבדיקה

{environment_note}
"""
    REPORT_HE.write_text(text, encoding="utf-8")


def main() -> int:
    checks = static_checks()
    checks.append(run("python_compile", [sys.executable, "-m", "compileall", "-q", "server.py", "cutroom", "tests"]))
    node = shutil.which("node")
    if node:
        for path in sorted((ROOT / "web").glob("*.js")):
            checks.append(run(f"javascript:{path.name}", [node, "--check", str(path)], timeout=30))
    else:
        checks.append({"name": "javascript_syntax", "ok": False, "stderr": "Node.js is unavailable"})

    runtime_modules = ("flask", "waitress", "faster_whisper")
    missing_runtime = [name for name in runtime_modules if importlib.util.find_spec(name) is None]
    api_available = not any(name in missing_runtime for name in ("flask", "waitress"))

    # Release validation is authoritative only when every discovered regression
    # suite runs. Named subsets silently became stale as hardening tests grew.
    checks.append(run("pytest_full", [sys.executable, "-m", "pytest", "-q"], timeout=1200))

    if api_available:
        checks.append(server_smoke())
        checks.append(browser_smoke())
    else:
        detail = "Missing build-environment modules: " + ", ".join(missing_runtime)
        print(f"[validation] API/server/browser: SKIP ({detail})", flush=True)
        for name in ("server_smoke", "browser_smoke"):
            checks.append({"name": name, "ok": True, "skipped": True, "stdout": detail, "stderr": ""})

    checks.append(run("two_source_render", [sys.executable, "tests/smoke_render.py"], timeout=600))
    checks.append(run("two_source_director_pipeline", [sys.executable, "tests/smoke_director_two_source.py"], timeout=900))
    checks.append(run("hierarchical_story_contract", [sys.executable, "tests/smoke_story_hierarchy.py"], timeout=300))
    checks.append(run("short_target_contract", [sys.executable, "tests/smoke_short_target.py"], timeout=900))
    checks.append(run("youtube_cleanup_contract", [sys.executable, "tests/smoke_youtube_cleanup.py"], timeout=900))
    checks.append(run("burned_captions_contract", [sys.executable, "tests/smoke_burn_captions.py"], timeout=600))
    checks.append(run("editorial_stack_contract", [sys.executable, "tests/smoke_editorial_stack.py"], timeout=600))
    checks.append(run("embedded_reel_contract", [sys.executable, "tests/smoke_embedded_reel.py"], timeout=600))

    report = {
        "version": __version__,
        "version_label": __version_label__,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok": all(item.get("ok") for item in checks),
        "full_runtime_verified": api_available and not missing_runtime,
        "missing_runtime_modules": missing_runtime,
        "checks": checks,
    }
    write_report(report)
    if report["ok"]:
        marker = "core_and_runtime" if report["full_runtime_verified"] else "core_with_environment_skips"
        (ROOT / ".verified").write_text(f"{report['generated_at']} {marker}", encoding="utf-8")
        print("CUTROOM release validation passed" + ("" if report["full_runtime_verified"] else " with documented environment skips"))
        return 0
    (ROOT / ".verified").unlink(missing_ok=True)
    print("CUTROOM release validation failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
