#!/usr/bin/env bash
# Doctor for verify-buildout: is this checkout worth driving?
# Read-only. Prints OK/FAIL per check; exit 0 iff all OK.
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
fails=0
check() { # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then echo "OK $1${3:+ — $3}"; else echo "FAIL $1${3:+ — $3}"; fails=$((fails+1)); fi
}

export PYTHONWARNINGS=ignore

ver=$("$REPO/bin/buildout" --version 2>/dev/null | tail -1)
[ -n "$ver" ]; check "bin/buildout --version" $? "$ver"

[ -x "$REPO/bin/test" ]; check "bin/test exists (make test runner)" $?
[ -x "$REPO/bin/py" ];   check "bin/py exists (make pytest runner)" $?
[ -x "$REPO/bin/coverage" ]; check "bin/coverage exists (coverage combine/report)" $?

pybin=$(ls -d "$REPO"/venvs/*/bin/python* 2>/dev/null | head -1)
[ -n "$pybin" ] && [ -x "$pybin" ]; check "venvs python" $? "$pybin"

[ -d "$REPO/eggs/v5" ]; check "eggs/v5 (pytest PYTHONPATH source)" $?

tyver=$(command -v ty >/dev/null 2>&1 && ty --version 2>/dev/null | head -1)
[ -n "$tyver" ]; check "ty on PATH (devenv, static tier)" $? "$tyver"

radonver=$(command -v radon >/dev/null 2>&1 && radon --version 2>/dev/null | head -1)
[ -n "$radonver" ]; check "radon on PATH (devenv, complexity tier)" $? "$radonver"

head_rev=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)
[ -n "$head_rev" ]; check "git HEAD" $? "$head_rev"
dirty=$(git -C "$REPO" status --short 2>/dev/null | head -5)
if [ -z "$dirty" ]; then echo "OK working tree clean"; else echo "NOTE working tree dirty:"; echo "$dirty"; fi

if [ "$fails" -gt 0 ]; then echo "DOCTOR: $fails FAIL — do not drive"; exit 1; fi
echo "DOCTOR: all checks passed"
