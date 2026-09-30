#!/bin/bash
set -euo pipefail
cutroom_pause_on_error() {
  local result=$?
  if [[ "$result" -ne 0 && "${CUTROOM_FINDER_LAUNCH:-}" == 1 && -t 0 ]]; then
    printf '\nCUTROOM stopped (code %s). The details are above.\n' "$result" >&2
    printf 'For help, open START HERE.html beside the launcher.\n' >&2
    printf '\nPress Return to close this window. '
    IFS= read -r unused || true
  fi
  exit "$result"
}
trap cutroom_pause_on_error EXIT
script_dir="$(cd "$(dirname "$0")" && pwd -P)"
source "$script_dir/setup_macos.sh"
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --check ) ]]; then
  printf 'Usage: /bin/bash run_macos.sh [--check]\n' >&2
  exit 2
fi
cutroom_prepare_environment
cd "$CUTROOM_APP_DIR"
if [[ "${1:-}" == --check ]]; then
  # CI/diagnostics: a check can never install or contact a package server.
  if [[ ! -x .venv/bin/python ]]; then
    printf 'CUTROOM has not been set up. Run START CUTROOM.command first.\n' >&2
    exit 1
  fi
  cutroom_runtime_ready
  exit 0
fi
if ! cutroom_runtime_ready >/dev/null 2>&1; then
  printf 'Checking the first-run setup or an incomplete local runtime...\n'
  /bin/bash "$CUTROOM_APP_DIR/setup_macos.sh"
  cutroom_prepare_environment
fi
cutroom_runtime_ready
printf '\nStarting CUTROOM. Keep this Terminal window open while editing.\n'
printf 'Press Control-C here to stop this CUTROOM server.\n\n'
# A same-process Python entry point keeps errors visible and forwards OS signals
# directly to the unchanged server, with no detached server child to clean up.
exec "$CUTROOM_APP_DIR/.venv/bin/python" "$CUTROOM_APP_DIR/preflight_macos.py" --launch
