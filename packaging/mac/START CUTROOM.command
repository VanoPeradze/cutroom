#!/bin/bash
# Finder entry point. Internal scripts do not depend on executable ZIP metadata.
set -u
package_dir="$(cd "$(/usr/bin/dirname "$0")" && pwd -P)" || exit 1
printf '\nCUTROOM AI — Mac Beta\n\n'
if [[ ! -f "$package_dir/App/run_macos.sh" ]]; then
  printf 'The App folder is missing. Extract the complete ZIP before starting CUTROOM.\n' >&2
  result=1
else
  export CUTROOM_FINDER_LAUNCH=1
  exec /bin/bash "$package_dir/App/run_macos.sh"
fi
if [[ "$result" -ne 0 ]]; then
  printf '\nCUTROOM stopped (code %s). The details are above.\n' "$result" >&2
  printf 'For help, open START HERE.html beside this launcher.\n' >&2
  if [[ -t 0 ]]; then
    printf '\nPress Return to close this window. '
    IFS= read -r unused || true
  fi
fi
exit "$result"
