#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  ./setup_linux.sh
fi
if ! .venv/bin/python scripts/preflight.py >/dev/null 2>&1; then
  echo "CUTROOM found an incomplete local runtime and will repair it."
  ./setup_linux.sh
fi
.venv/bin/python scripts/preflight.py
exec .venv/bin/python server.py
