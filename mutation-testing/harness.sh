#!/bin/bash
# Mutation kill-matrix: legacy (bin/test -t configuration.txt) vs pytest mirror.
# rc=0 means suite GREEN = mutant SURVIVED; rc!=0 = KILLED.
cd /Users/gotcha/co/buildout-wt-mutation
F=src/zc/buildout/buildout.py
PYF=src/zc/buildout/tests/pytests/test_pytest_buildout_txt.py
EGGS=$(ls -d $PWD/eggs/v5/*.egg | tr '\n' ':')
apply() { python3 - "$1" "$2" <<'PY'
import sys
old, new = sys.argv[1], sys.argv[2]
p = 'src/zc/buildout/buildout.py'
s = open(p).read()
assert old in s, "PATTERN NOT FOUND"
open(p, 'w').write(s.replace(old, new, 1))
PY
}
run_one() {
  local name="$1" old="$2" new="$3"
  git restore $F 2>/dev/null
  if [ -n "$old" ]; then apply "$old" "$new" || { echo "$name APPLY_FAIL"; return; }; fi
  PYTHONWARNINGS=ignore bin/test -pvc -t configuration.txt >/dev/null 2>&1; local L=$?
  PYTHONWARNINGS=ignore PYTHONPATH="$EGGS" bin/py -m pytest "$PYF" -q >/dev/null 2>&1; local P=$?
  echo "$name legacy_rc=$L pytest_rc=$P"
}
run_one M0-baseline
run_one M1-raw-always '            value = self[section].get(option)' '            pass'
run_one M2-empty-side-ok '        if not section or not option:' '        if False and section:'
run_one M3-multi-colon-ok '        elif len(option) != 2:' '        elif len(option) > 3:'
run_one M4-missing-key-none '            value = self._raw[section][option]' '            value = self._raw.get(section, {}).get(option)'
run_one M5-annotate-raw '            data = self._interpolated_annotated()' '            data = self._annotated'
run_one M6-none-guard-off '                if value is not None:' '                if value is not None or value is None:'
run_one M7-shallow-copy '        data = copy.deepcopy(self._annotated)' '        data = copy.copy(self._annotated)'
git restore $F 2>/dev/null
echo "final tree: $(git status --short $F | wc -l | tr -d ' ') dirty"
