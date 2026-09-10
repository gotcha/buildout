# Per-pytest-module kill matrices

Date: 2026-09-10. Gotcha's order (thread 06121844): "do the same as you
did on configuration.txt, iterating on the pytest modules". Each section
below is one pytest module: semantic mutations on the source region the
module exercises, run against BOTH the legacy scoped suite
(`bin/test -pvc -t <name>`) and the pytest module; rc=0 → mutant
SURVIVED, rc≠0 → KILLED. Mutants applied as exact-string replaces,
`git restore` between rounds. The configuration.txt ↔
test_pytest_buildout_txt.py matrix is in NOTES.md (M1–M7).

## test_pytest_extras.py ↔ legacy `test_extras` (easy_install.py extras region)

Region: `Installer._satisfied` extras handling (~easy_install.py
923-956) — the "extras in requirements were lost" bugfix region.

| Mutation | legacy | pytest |
|---|---|---|
| X1 extra requirements dropped (`dist.requires(req.extras)` → `[]`) | KILL | KILL |
| X2 missing-extra check inverted (`-` → `&`) | KILL | KILL |
| X3 `_allow_unknown_extras` condition flipped | survive | survive |
| X4 requires called with no extras (`requires(())`) | KILL | KILL |

Agreement 4/4. X3 survives both: the module's test exercises no
missing-extra path (that path belongs to allow-unknown-extras.txt, see
test_pytest_easy_install_files.py). Kills under X1/X4 confirm both
suites really resolve the extra's dependency through this code.

## test_pytest_rmtree.py ↔ legacy `rmtree` (zc/buildout/rmtree.py)

| Mutation | legacy | pytest |
|---|---|---|
| RM0 baseline | pass | pass |
| RM1 rmtree gutted (`shutil.rmtree(...)` → `pass`) | KILL | KILL |
| RM2 handler chmod dropped | survive | survive |
| RM3 retry loop `range(10)` → `range(0)` | survive | survive |
| RM4 handler swallows instead of re-raise | survive | survive |

Agreement 4/4. Finding: the retry/chmod error handler is
Windows-oriented; on POSIX, unlinking a read-only file inside a
writable directory never triggers `onerror`, so handler mutants are
unexercised in BOTH suites (verified 3× after one flaky batch read —
always re-run a surprising one-suite kill before believing it). Same
coverage gap in both suites: no divergence.
