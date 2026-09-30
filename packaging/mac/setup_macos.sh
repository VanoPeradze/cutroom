#!/bin/bash
# Mac-only setup. Safe to source for local discovery; sourcing installs nothing.
set -euo pipefail

CUTROOM_APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

cutroom_help() {
  printf '\nMac setup help: open START HERE.html in the mac folder.\n' >&2
  printf 'Homebrew: https://brew.sh/\nPython: https://www.python.org/downloads/macos/\n' >&2
  printf 'Compatible FFmpeg 7: https://formulae.brew.sh/formula/ffmpeg@7\n' >&2
  if [[ -f "$CUTROOM_APP_DIR/../START HERE.html" ]] && command -v open >/dev/null 2>&1; then
    open "$CUTROOM_APP_DIR/../START HERE.html" >/dev/null 2>&1 || true
  fi
}

cutroom_prepare_environment() {
  # Finder normally supplies only system paths. Do not evaluate shell profiles.
  local machine native_prefix other_prefix candidate brew_prefix os_version
  machine="$(uname -m)"
  if [[ "$(uname -s)" != Darwin ]]; then
    printf 'This launcher requires a Mac. Use the windows folder on Windows.\n' >&2
    return 1
  fi
  os_version="$(sw_vers -productVersion)"
  if [[ "${os_version%%.*}" -lt 15 ]]; then
    printf 'This Mac beta requires macOS 15 or later (found %s).\n' "$os_version" >&2
    cutroom_help
    return 1
  fi
  if [[ "$(/usr/sbin/sysctl -in hw.optional.arm64 2>/dev/null || true)" == 1 ]]; then
    machine=arm64
  fi
  case "$machine" in
    arm64) native_prefix=/opt/homebrew; other_prefix=/usr/local ;;
    x86_64) native_prefix=/usr/local; other_prefix=/opt/homebrew ;;
    *) printf 'Unsupported Mac architecture: %s\n' "$machine" >&2; return 1 ;;
  esac
  export CUTROOM_MAC_ARCH="$machine"
  export PATH="$native_prefix/opt/ffmpeg@7/bin:$native_prefix/bin:$native_prefix/sbin:$other_prefix/opt/ffmpeg@7/bin:$other_prefix/bin:$other_prefix/sbin:${PATH:-/usr/bin:/bin}:/usr/bin:/bin:/usr/sbin:/sbin"
  if [[ -n "${HOME:-}" ]]; then
    export PATH="$PATH:$HOME/.local/bin"
  fi
  # Custom Homebrew prefixes are supported without forcing a global link.
  if command -v brew >/dev/null 2>&1; then
    brew_prefix="$(HOMEBREW_NO_AUTO_UPDATE=1 brew --prefix ffmpeg@7 2>/dev/null || true)"
    if [[ -n "$brew_prefix" && -d "$brew_prefix/bin" ]]; then
      export PATH="$brew_prefix/bin:$PATH"
    fi
  fi
  if [[ -z "${CUTROOM_OLLAMA:-}" ]]; then
    for candidate in "/Applications/Ollama.app/Contents/Resources/ollama" "/Applications/Ollama.app/Contents/MacOS/ollama" "${HOME:-}/Applications/Ollama.app/Contents/Resources/ollama" "${HOME:-}/Applications/Ollama.app/Contents/MacOS/ollama"; do
      if [[ -x "$candidate" ]]; then
        export CUTROOM_OLLAMA="$candidate"
        break
      fi
    done
  fi
}

cutroom_python_supported() {
  "$1" -c 'import os, platform, sys; expected = os.environ.get("CUTROOM_MAC_ARCH"); raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) and (not expected or platform.machine() == expected) else 1)' >/dev/null 2>&1
}

cutroom_resolve_python() {
  local candidate
  if [[ -n "${CUTROOM_PYTHON:-}" ]]; then
    if cutroom_python_supported "$CUTROOM_PYTHON"; then
      printf '%s\n' "$CUTROOM_PYTHON"
      return 0
    fi
    printf 'CUTROOM_PYTHON must name a native Python 3.11 or 3.12 executable.\n' >&2
    return 1
  fi
  for candidate in python3.12 python3.11 /opt/homebrew/opt/python@3.12/bin/python3.12 /usr/local/opt/python@3.12/bin/python3.12 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && cutroom_python_supported "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

cutroom_system_ready() {
  local python_bin="$1"
  "$python_bin" "$CUTROOM_APP_DIR/preflight_macos.py" --system-only
}

cutroom_overrides_ready() {
  if [[ -z "${CUTROOM_FFMPEG:-}" && -z "${CUTROOM_FFPROBE:-}" ]]; then return 0; fi
  if ! "$1" "$CUTROOM_APP_DIR/preflight_macos.py" --overrides-only; then
    printf 'A custom CUTROOM_FFMPEG/CUTROOM_FFPROBE path is incompatible. Correct it or unset it to use ffmpeg@7, then launch again.\n' >&2
    return 1
  fi
}

cutroom_runtime_ready() {
  [[ -x "$CUTROOM_APP_DIR/.venv/bin/python" ]] || return 1
  cutroom_python_supported "$CUTROOM_APP_DIR/.venv/bin/python" || return 1
  "$CUTROOM_APP_DIR/.venv/bin/python" "$CUTROOM_APP_DIR/preflight_macos.py"
}

cutroom_setup_main() {
  local consent=no python_bin='' brew_bin='' need_python=no need_ffmpeg=no repair_python=no answer backup_dir
  if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --yes ) ]]; then
    printf 'Usage: /bin/bash setup_macos.sh [--yes]\n--yes explicitly approves the dependency downloads described below.\n' >&2
    return 2
  fi
  if [[ "${1:-}" == --yes ]]; then consent=yes; fi
  cutroom_prepare_environment
  cd "$CUTROOM_APP_DIR"
  if [[ ! -f requirements.txt || ! -f constraints-macos.txt || ! -f server.py || ! -f preflight_macos.py ]]; then
    printf 'CUTROOM is incomplete. Extract the entire download again.\n' >&2
    return 1
  fi
  if [[ ! -w "$CUTROOM_APP_DIR" ]]; then
    printf 'CUTROOM needs a writable folder. Move the extracted mac folder to Documents or Applications in your home folder.\n' >&2
    return 1
  fi
  if cutroom_runtime_ready >/dev/null 2>&1; then
    printf 'CUTROOM is ready. No downloads are needed.\n'
    return 0
  fi
  python_bin="$(cutroom_resolve_python)" || need_python=yes
  if [[ -n "${CUTROOM_PYTHON:-}" && "$need_python" == yes ]]; then return 1; fi
  if [[ "$need_python" == yes ]]; then
    need_ffmpeg=yes
  else
    cutroom_overrides_ready "$python_bin"
    if ! cutroom_system_ready "$python_bin"; then need_ffmpeg=yes; fi
  fi
  brew_bin="$(command -v brew || true)"
  if [[ ( "$need_python" == yes || "$need_ffmpeg" == yes ) && -z "$brew_bin" ]]; then
    printf '\nPython 3.11/3.12 and compatible FFmpeg with libass, libx264 and AAC are required.\n' >&2
    printf 'Homebrew is not installed. Install it using the official website, then run:\n' >&2
    printf '  brew install python@3.12 ffmpeg@7\n' >&2
    printf 'Then double-click START CUTROOM.command again. Setup will ask before installing Python packages.\n' >&2
    cutroom_help
    return 1
  fi
  printf '\nCUTROOM needs to install or repair its Mac runtime.\n'
  if [[ "$need_python" == yes ]]; then printf '  • Install native Python 3.12 using your existing Homebrew.\n'; fi
  if [[ "$need_ffmpeg" == yes ]]; then printf '  • Install ffmpeg@7 using your existing Homebrew (compatible rendering and subtitle support).\n'; fi
  printf '  • Install Python packages listed in App/requirements.txt into App/.venv.\n'
  printf 'This requires internet access and free disk space. AI models are not downloaded.\n'
  if [[ "$consent" != yes ]]; then
    printf '\nType yes to approve these downloads, or press Return to cancel: '
    IFS= read -r answer || answer=''
    answer="${answer%$'\r'}"
    case "$answer" in yes|YES|Yes) consent=yes ;; *)
      printf 'Setup cancelled. Nothing has been installed. Run the launcher when you are ready.\n'
      return 1 ;;
    esac
  else
    printf 'Downloads approved with --yes.\n'
  fi
  # One setup at a time; never kill another app or remove another setup's files.
  CUTROOM_SETUP_LOCK="$CUTROOM_APP_DIR/.setup-macos.lock"
  if ! mkdir "$CUTROOM_SETUP_LOCK" 2>/dev/null; then
    printf 'Another setup may be running. Wait for it to finish. If no setup is running, remove the empty App/.setup-macos.lock folder and try again.\n' >&2
    return 1
  fi
  trap 'rmdir "$CUTROOM_SETUP_LOCK" 2>/dev/null || true' EXIT
  if [[ "$need_python" == yes ]]; then
    HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 "$brew_bin" install python@3.12
    cutroom_prepare_environment
    python_bin="$(cutroom_resolve_python)" || { printf 'A native Python 3.11/3.12 still could not be found.\n' >&2; cutroom_help; return 1; }
    cutroom_overrides_ready "$python_bin"
  fi
  if [[ "$need_ffmpeg" == yes ]]; then
    HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 "$brew_bin" install ffmpeg@7
  fi
  cutroom_prepare_environment
  python_bin="$(cutroom_resolve_python)" || { printf 'A native Python 3.11/3.12 still could not be found.\n' >&2; cutroom_help; return 1; }
  if ! cutroom_system_ready "$python_bin"; then
    printf 'FFmpeg is still unavailable or lacks required codecs/options. Check CUTROOM_FFMPEG/CUTROOM_FFPROBE if you set custom paths.\n' >&2
    cutroom_help
    return 1
  fi
  if [[ -L .venv || ( -e .venv && ! -d .venv ) ]]; then
    printf 'App/.venv is not a regular directory. Move it aside and launch again.\n' >&2
    return 1
  fi
  if [[ -d .venv ]] && ! cutroom_python_supported "$CUTROOM_APP_DIR/.venv/bin/python"; then
    backup_dir="$CUTROOM_APP_DIR/.venv.previous-$(date +%Y%m%d-%H%M%S)-$$"
    mv "$CUTROOM_APP_DIR/.venv" "$backup_dir"
    printf 'Previous Python environment preserved at %s\n' "$backup_dir"
  fi
  if [[ ! -x .venv/bin/python ]]; then
    "$python_bin" -m venv .venv
  elif ! .venv/bin/python preflight_macos.py --python-only >/dev/null 2>&1; then
    repair_python=yes
  fi
  .venv/bin/python -m pip install --disable-pip-version-check --upgrade pip wheel setuptools
  if [[ "$repair_python" == yes ]]; then
    .venv/bin/python -m pip install --disable-pip-version-check --force-reinstall -r requirements.txt -c constraints-macos.txt
  else
    .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt -c constraints-macos.txt
  fi
  .venv/bin/python preflight_macos.py
  printf '\nCUTROOM Mac setup completed. Starting the editor is now possible offline.\n'
  rmdir "$CUTROOM_SETUP_LOCK"
  trap - EXIT
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  cutroom_setup_main "$@"
fi
