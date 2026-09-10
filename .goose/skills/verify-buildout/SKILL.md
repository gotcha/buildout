---
name: verify-buildout
description: Verify zc.buildout behavior by driving the real CLI the way a user does — running bin/buildout from this checkout against throwaway projects, inspecting state with query/annotate, and running the repo's two test suites (make test / make pytest). Use when a change to this repo needs behavioral proof beyond unit tests.
---

# Verify buildout

zc.buildout is a CLI: a user writes a `buildout.cfg`, runs `buildout`,
and expects parts installed, scripts generated, and state queryable.
This skill drives exactly that loop with the `bin/buildout` built from
this checkout, plus the repo's two test suites as the deep proof layer.

This skill is location-independent: it lives at
`.goose/skills/verify-buildout/` inside the checkout. Set `REPO` to the
checkout root on the current machine (the helper scripts derive it
from their own location, e.g.
`REPO=$(cd "$(dirname "$0")/../../../.." && pwd)` in `helpers/`).
No machine-specific path or branch name appears anywhere in this skill.
All commands assume
`export PYTHONWARNINGS=ignore` — the checkout still imports
`pkg_resources` on startup and the deprecation warning otherwise
pollutes every transcript.

## Launch

Buildout is a short-lived CLI — there is no server. "Launch" means:
build the runner once, then start each drive in its own throwaway
project directory.

One-time build (already done in a fresh checkout only if `bin/` is
missing):

```sh
cd $REPO
make bin/buildout        # = ./prepare.sh: venv in venvs/, pip deps, sdist, dev.py
```

Known-good pin on this machine: `PYTHON_VERSION=3.12 SETUPTOOLS_VERSION=75.8.2`
(the default unpinned setuptools can break the 5.x bootstrap).

Per-drive launch:

```sh
D=$(mktemp -d /tmp/verify-buildout.XXXXXX) && cd "$D"
printf '[buildout]\nparts =\n' > buildout.cfg
```

Ready check: `bin/buildout --version` prints `buildout version 5.2.x`
without a traceback.

Teardown: `rm -rf "$D"` — but only AFTER evidence is copied out (see
Evidence). Never run drives in the repo root: `bin/buildout` there
rewrites `.installed.cfg`, `parts/`, `eggs/` — shared state the test
suites depend on.

## Doctor

One read-only check answering "is this checkout worth driving?". Run
the helper (ships with this skill, executable):

```sh
$REPO/.goose/skills/verify-buildout/helpers/doctor.sh
```

It checks, printing OK/FAIL per line and exiting non-zero on any FAIL:

- `bin/buildout --version` runs and reports 5.2.x (runner built, importable)
- `bin/test` and `bin/py` exist (suite runners ready)
- `venvs/` has a python (bootstrap venv present)
- `git -C <repo> rev-parse HEAD` and `status --short` — record the exact
  revision driven, and whether the tree was dirty
- `eggs/v5/` exists (pytest suite needs its eggs on PYTHONPATH)

Run the doctor first whenever anything looks off; a FAIL there
invalidates everything downstream. If `bin/buildout` is missing,
rebuild with `make bin/buildout` (pins above).

## Drive

Harness: plain shell. The app under test is
`$REPO/bin/buildout` — a dev install of
this checkout, so every drive exercises the current source tree. Every
drive runs in its own `mktemp -d` project dir with its own
`buildout.cfg`. That is complete isolation: two drives can run side by
side as long as each has its own `$D`. The only shared, mutable state
is the pip download cache (`~/.cache/pip`) — reads/writes there are
safe but mean "offline" behavior is not truly hermetic unless pip is
starved; see Gotchas in the feature files.

Feature recipes live in [`features/`](./features/README.md) — read the
index, then follow the feature file. The tiers:

1. **Hermetic** (no network): empty-parts install, rerun modes,
   `query`/`annotate`, command-line assignments, `-U`.
2. **Networked**: real part install (`zc.recipe.egg` via local
   `develop`, published egg from PyPI), `init`/`bootstrap`. Requires
   network or a warm pip cache.
3. **Suites** (the deep proof): the repo has TWO suites, run from the
   repo root:
   - `make test` — legacy doctest/testrunner suite (`bin/test -pvc`).
     Several minutes. Scoped smoke: `make test-small` (single
     `buildout.txt` file) or `bin/test -pvc -t <name>`.
   - `make pytest` — ported pytest suite in
     `src/zc/buildout/tests/pytests/`, run with xdist
     (`bin/py -m pytest ... -n auto`). The Makefile passes
     `PYTHONPATH=eggs/v5/*.egg` because xdist workers are bare
     interpreters that do not inherit `bin/py`'s baked sys.path — if
     you invoke pytest by hand, you MUST set that PYTHONPATH yourself.
     Scoped smoke: one file, e.g. `... test_pytest_rmtree.py -q`.

## Evidence

Capture per drive, into a named artifacts dir that survives cleanup —
use `ART=/tmp/verify-buildout-artifacts-$(date +%Y%m%d-%H%M%S)` and
`mkdir -p "$ART"`; cleanup removes project dirs, never `$ART`.

Proof standards:

- Record per drive: the exact `buildout.cfg` used, the command, exit
  code, full stdout/stderr transcript (`| tee "$ART/<name>.log"`), and
  `git rev-parse HEAD` of the checkout.
- Capture the action AND the resulting state: after an install, list
  the tree (`ls -la`, `ls bin/`) and read back state through a second,
  read-only view: `bin/buildout query section:option` and
  `bin/buildout annotate` (shows each value's origin file — DEFAULT /
  config / COMMAND_LINE_VALUE).
- Verify side effects on disk, not just output: `.installed.cfg`
  contents, generated scripts in `bin/`, egg links in `develop-eggs/`.
  Note: with `parts =` empty, NO `.installed.cfg` is written — that is
  expected, assert it, don't "fix" it.
- For the suites: keep the final summary line (testrunner totals or
  pytest `passed/failed` line) plus the scoped or full run duration.
- Mocks: none. The only sanctioned offline substitution is the
  hermetic tier itself; never stub PyPI.

## Cleanup

- `rm -rf` each drive's project dir `$D` — only after evidence is in
  `$ART`. Nothing else: buildout is short-lived, no processes survive
  a drive.
- Never kill by process name. If a suite run must be aborted, kill the
  exact PID you started; xdist children exit with their parent.
- Do NOT run `make clean` as cleanup: it deletes `bin/`, `venvs/`,
  `eggs/` — the built environment the next run needs. `make clean` is
  a bootstrap reset, not drive cleanup.
- Proof artifacts in `$ART` are never removed by cleanup.

## Helpers

- [`helpers/doctor.sh`](./helpers/doctor.sh) — the Doctor check
  described above. Usage: `doctor.sh` (no args; absolute paths baked
  in). Prints `OK <check>` / `FAIL <check>`, exit 0 iff all OK.

## Feature map

See [`features/README.md`](./features/README.md). Current coverage:
install-and-inspect (hermetic core), configure-and-substitute,
rerun-modes, project scaffolding (init/bootstrap, networked), and the
two repo test suites.
