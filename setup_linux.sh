#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
resolve_python() {
  local candidate
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)' >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

python_bin=$(resolve_python) || { echo "Python 3.11 or 3.12 is required."; exit 1; }
command -v ffmpeg >/dev/null || { echo "FFmpeg is required. Install it with your distribution package manager."; exit 1; }
command -v ffprobe >/dev/null || { echo "FFprobe is required. Install the full FFmpeg package."; exit 1; }
"$python_bin" -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel setuptools
.venv/bin/python -m pip install -r requirements.txt
if command -v ollama >/dev/null; then
  model=$(.venv/bin/python -c "import json; print(json.load(open('config.json'))['ai']['editor_model'])")
  download=$(.venv/bin/python -c "import json; print(str(json.load(open('config.json'))['ai']['download_models_on_setup']).lower())")
  if [[ "$download" == "true" ]]; then ollama pull "$model" || true; fi
fi
.venv/bin/python -m compileall -q server.py cutroom
.venv/bin/python scripts/preflight.py
printf 'CUTROOM AI 5.6.1 setup completed\n' > .setup-complete
echo "CUTROOM is ready. Run ./run_linux.sh"
