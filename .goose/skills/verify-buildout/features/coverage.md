# Coverage variants of the test suites

Both repo test suites have a coverage variant: `make coverage` (legacy
doctest/testrunner suite) and `make coverage-pytest` (ported pytest
suite). They answer "what of `src/zc/buildout` does this suite actually
execute" — including the code run by the many spawned `bin/buildout`
and pip subprocesses, which is where most of buildout's behavior lives.

## How it works

One mechanism covers every process, no per-suite hooks:

- `etc/coverage/sitecustomize.py` goes on `PYTHONPATH` (the Makefile
  `COVERAGE_ENV` does this, together with the `eggs/v5/*.egg` entries so
  the coverage egg is importable everywhere, including xdist workers —
  same reason as `make pytest`). Python imports `sitecustomize` at
  interpreter startup; the hook checks `COVERAGE_PROCESS_START` and
  calls `coverage.process_startup()`. Every interpreter in the run —
  the suite process, xdist workers, test-spawned `bin/buildout`
  scripts, pip — starts its own tracer before importing anything, so
  module-level lines are measured too.
- `.coveragerc` sets `parallel = true`: each process writes its own
  `.coverage.<host>.<pid>.<rand>` data file. An absolute
  `COVERAGE_FILE` (also in `COVERAGE_ENV`) keeps them all in the repo
  root — `bin/test` exits with `parts/test` as cwd and test-spawned
  processes chdir into throwaway dirs, so a relative data file would
  scatter or vanish.
- `[paths]` in `.coveragerc` folds the fake-release eggs the update
  tests build (`*/eggs/v5/zc.buildout-*.egg/zc/buildout`) back onto
  `src/zc/buildout` — they package the current source, and without the
  mapping `coverage report` aborts with "No source for code" once the
  tmpdirs are gone.
- After the suite, `bin/coverage combine` merges the data files and
  `bin/coverage report` / `bin/coverage html` render them. Use
  `bin/coverage`, never `python -m coverage`: the bare venv python has
  no coverage installed (coverage comes from the `[py]` eggs).
- `[run] disable_warnings = trace-changed` exists because the
  debugging tests drop into pdb, which replaces the trace function;
  coverage's warning would otherwise pollute that subprocess's
  expected output.

History: the pre-sitecustomize machinery (`setup_coverage()` gated on
`RUN_COVERAGE`, plus `buildoutSetUp` patching the sample `bin/buildout`
script) was removed — the patched script could not import coverage,
and the patch made a later buildout run regenerate the script, adding
output lines that broke `allowhosts`-style tests.

## What the numbers mean

- `source = zc.buildout` is matched by module name, so only code
  imported as `zc.buildout.*` is measured — the library, and under the
  legacy suite the test modules too (testrunner imports them as
  `zc.buildout.tests.*`).
- Under pytest, test modules are imported as `buildout.tests.*`
  (pytest walks up from `pytests/` and `src/zc/` has no `__init__.py`),
  so pytest-side reports show the test files themselves at 0% — a
  naming artifact, not missing coverage of the library. Compare
  library modules across suites, not TOTAL lines.
- The two suites exercise different amounts of the library; expect the
  legacy report to be the higher, authoritative one.

## Sub-features

- `coverage-legacy` — `make coverage`: full legacy suite under
  coverage, then combine/report/html. Slow: the suite is ~8-10 min
  plain, and coverage 5.1 runs without its C extension here (pure
  Python tracer), so budget roughly 3x that. The official coverage
  truth.
- `coverage-pytest` — `make coverage-pytest`: pytest suite under
  coverage (~3-4 min with xdist). The fast coverage loop.
- `coverage-scoped` — hand runs for iteration, mirroring
  `suite-scoped`: set the same env as the Makefile (`COVERAGE_ENV`)
  and scope the suite, e.g. `bin/test -pvc -t buildout.txt` or one
  pytest file with `-n 2`.

## How to get to it (user POV)

- Repo root: `make coverage`, `make coverage-pytest`. Reports print to
  the console; HTML lands in `htmlcov/`.
- CI: the `coverage legacy` and `coverage pytest` jobs run in parallel
  with the windows job and upload `htmlcov/` as artifacts
  (`coverage-legacy-html`, `coverage-pytest-html`).

## Driving it with shell

Preconditions: doctor all-OK; run from the repo root (suites drive in
the repo root, see repo-test-suites).

- `make coverage 2>&1 | tee "$ART/make-coverage.log"`. Exit 0; capture
  the testrunner totals line AND the report TOTAL line.
- `make coverage-pytest 2>&1 | tee "$ART/make-coverage-pytest.log"`.
  Exit 0; capture the pytest `passed` line and the report TOTAL line.
- Cleanup between runs is in the targets (`rm -f .coverage .coverage.*`).
  Never glob `.coverage*` by hand: it also matches `.coveragerc`.
- A report that aborts with `No source for code: ...` means a
  subprocess ran zc.buildout from a path that no longer exists and the
  `[paths]` mapping needs a new entry — do not paper over it with
  `coverage report -i` without understanding which path appeared.

## Gotchas

- All the `make pytest` PYTHONPATH gotchas apply (see
  repo-test-suites): if you invoke the coverage variants by hand,
  replicate the Makefile's `COVERAGE_ENV` exactly.
- Never run the two coverage suites (or any suites) concurrently —
  same CPU-starvation flakiness as the plain suites.
- `htmlcov/` and `.coverage*` are run artifacts; `.gitignore` covers
  them, but clean them when switching branches if a stale report
  confuses you: `rm -rf htmlcov .coverage .coverage.*`.
- The sitecustomize hook is import-tolerant on purpose: a Python
  process that has the env vars but no coverage egg importable runs
  untraced instead of crashing the suite.
