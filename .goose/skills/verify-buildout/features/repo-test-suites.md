# Repo test suites

Buildout's own behavior specification is executable and comes in two
suites: the legacy doctest/testrunner suite (`make test`) and the
ported pytest suite (`make pytest`). For a behavior-affecting change,
these are the deep proof layer beneath the CLI drives.

## Which suite proves what

- **The legacy suite (`make test`) is the official truth.** The
  pytest suite is a port and still too young to stand alone — a
  change is NOT verified until `make test` passes. Fast loops defer,
  never replace: every verification ends with the legacy suite.
- **The pytest suite is the development loop.** It is much quicker
  (~1 min vs ~8+ min for a full run), so iterate with it while
  developing — scoped single files, then full `make pytest` — then
  prove the change with `make test`.
- **Divergence rule:** if the legacy suite fails while the pytest
  suite passes, the pytest port is wrong — fix the pytest suite to
  match the legacy behavior, not the other way around.
- **Changing tested behavior:** when a change impacts existing tests,
  update BOTH suites in the same change.

## Sub-features

- `suite-doctest` — `make test` runs the zope.testrunner doctest suite
  (`bin/test -pvc`). Several minutes. The official truth.
- `suite-pytest` — `make pytest` runs `src/zc/buildout/tests/pytests/`
  under xdist (`-n auto`). Much faster — the development loop.
- `suite-scoped` — both suites support scoped runs for fast iteration:
  `make test-small` (or `bin/test -pvc -t buildout.txt`) and
  single-file pytest invocations.

## How to get to it (user POV)

- Repo root: `make test`, `make pytest`, `make test-small`.
- Hand-rolled scoped: `bin/test -pvc -t <test-name>`;
  `bin/py -m pytest src/zc/buildout/tests/pytests/test_<x>.py -q`.

## Driving it with shell

Preconditions:

- Doctor all-OK (both `bin/test` and `bin/py` present, `eggs/v5/`
  populated); run from the repo root — this is the ONE feature that
  drives in the repo root, because the suites are built to.
- Full runs go to `$ART`: `make test 2>&1 | tee "$ART/make-test.log"`.

- **Doctest suite.** `make test 2>&1 | tee "$ART/make-test.log"`.
  Exit 0; final lines report the testrunner totals
  (`Total: N tests, 0 failures, 0 errors ...`). Capture that line.
- **Pytest suite.** `make pytest 2>&1 | tee "$ART/make-pytest.log"`.
  Exit 0; final line `N passed ...`. Capture it.
- **Scoped smoke (fast proof).** `make test-small` and
  `PYTHONWARNINGS=ignore PYTHONPATH="$(ls -d $PWD/eggs/v5/*.egg | tr '\n' ':')" \
    bin/py -m pytest src/zc/buildout/tests/pytests/test_pytest_rmtree.py -q`.
  Both exit 0. Use these when the full suites are too slow for the
  question at hand, and say so in the report — a scoped smoke is
  iteration fuel, never the final proof (see "Which suite proves
  what").

## Gotchas

- Hand-invoking pytest WITHOUT the `PYTHONPATH=eggs/v5/*.egg` line
  breaks xdist workers (they are bare interpreters and do not inherit
  `bin/py`'s baked sys.path) — the Makefile comment says exactly this.
  Use `make pytest`, or replicate the PYTHONPATH.
- `make test` rebuilds `bin/test` via `bin/buildout` if the config
  changed — a suite run can rewrite repo-root state. That is normal;
  the doctor's dirty-tree NOTE records it.
- Both suites spawn subprocesses heavily; run them sequentially, never
  concurrently (`-n auto` plus the testrunner starves CPU and causes
  flaky timeouts).
- If `bin/` or `venvs/` is missing, rebuild first with the known-good
  pin: `PYTHON_VERSION=3.12 SETUPTOOLS_VERSION=75.8.2 make bin/buildout`.
- Failure triage: a red suite on an UNMODIFIED checkout means the
  environment drifted (new setuptools/pip), not necessarily the code —
  record `bin/py -m pip --version` and the venv's `pip freeze` into
  `$ART` before concluding anything.
- Suite disagreement is a pytest-port bug: legacy red + pytest green
  means the pytest suite must be fixed to match legacy. Behavior
  changes that impact existing tests update BOTH suites in the same
  change.
