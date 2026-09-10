# Per-pytest-module kill matrices

Date: 2026-09-10. Gotcha's order (thread 06121844): "do the same as you
did on configuration.txt, iterating on the pytest modules". Each section
below is one pytest module: semantic mutations on the source region the
module exercises, run against BOTH the legacy scoped suite
(`bin/test -pvc -t <name>`) and the pytest module; rc=0 → mutant
SURVIVED, rc≠0 → KILLED. Mutants applied as exact-string replaces,
`git restore` between rounds. The configuration.txt ↔
test_pytest_buildout_txt.py matrix is in NOTES.md (M1–M7).

## test_pytest_buildout_doctests.py ↔ legacy inline doctests in test_all.py

Legacy side scoped per mutant with a tailored `-t` regex naming the
mirrored doctest functions.

| Mutation | legacy | pytest |
|---|---|---|
| D1 who-requires filter inverted (`in` → `not in` in `_version_conflict_information`) | KILL (`-t 'show_who_requires\|version_conflict'`) | KILL |
| D2 `-v` decrements verbosity instead of incrementing | KILL (`-t develop_verbose`) | KILL |
| D3 `-o` sets `offline=false` instead of `true` | KILL (`-t o_option_sets_offline`) | KILL |

Agreement 3/3, all kills across conflict-reporting and CLI-flag
regions.

## test_pytest_buildout_files.py ↔ legacy runsetup.txt + repeatable.txt + setup.txt + debugging.txt + windows.txt

Legacy side run as one scoped regex:
`bin/test -pvc -t 'runsetup.txt|repeatable.txt|setup.txt|debugging.txt|windows.txt'`.

| Mutation | legacy | pytest |
|---|---|---|
| B1 runsetup drops extra args (`+ args` removed) | KILL | KILL |
| B2 `While:` reporting suppressed (`if d:` → `if False:` in `_doing`) | KILL | KILL |
| B3 `While:` formatting broken (isinstance check inverted) | KILL | KILL |

Agreement 3/3, all kills — the runsetup/setup and debugging
(`While:`) regions are equally covered by both suites.

## test_pytest_configparser.py ↔ legacy `configparser.test` (zc/buildout/configparser.py)

| Mutation | legacy | pytest |
|---|---|---|
| C1 `=>` shorthand broken (`== '=>'` → `== '=='`) | KILL | KILL |
| C2a conditional-section filter inverted | KILL | KILL |
| C2b conditional option filter removed (`continue` → `pass`) | KILL | KILL |
| C3 `-=` treated as assignment (`'+-'` → `'+'`) | KILL | KILL |
| C4 multiline dedent skipped (`isspace()` → `isdigit()`) | KILL | KILL |

Agreement 5/5, all kills — the conditional-section / marker / comment
machinery is tightly and equally covered by both suites.

## test_pytest_increment.py ↔ legacy `test_increment` (`_update_section`/`_update`, buildout.py ~2081-2150)

| Mutation | legacy | pytest |
|---|---|---|
| I1 `+=` behaves as `-=` (addToValue → removeFromValue) | KILL | KILL |
| I2 +/- sort key widened (`rstrip(' +')` → `rstrip(' +-')`) | survive | survive |
| I3 implicit += base non-empty (`""` → `"x"`) | KILL | KILL |
| I4 no-base `+=`/`-=` branches swapped in `_update` | survive | survive |

Agreement 4/4. I2's sort-key change alters no exercised ordering; I4
is the instructive survivor: `+=` without a preceding `=` that escapes
`_update`'s normalization is still caught by `_update_section`'s `+=`
branch (addToValue against an implicit empty base) — compensating
layers make the mutant semantically invisible to both suites.

## test_pytest_update.py ↔ legacy `update.txt` (self-update region, buildout.py ~1164-1260)

| Mutation | legacy | pytest |
|---|---|---|
| U1 newest check flipped (`if not self.newest` → `if self.newest`) | KILL | KILL |
| U2 restart-guard env var neutralized | survive | survive |
| U3 upgrade projects trimmed to `('zc.buildout',)` | survive | survive |
| U4 upgraded check flipped (`if not upgraded` → `if upgraded`) | KILL | KILL |

Agreement 4/4. U2 survives both: after a real restart the upgrade
check re-runs but finds nothing new, so the missing guard is invisible
to CLI-level output. U3 survives both: the test env only publishes a
new zc.buildout release, so dropping wheel/pip/setuptools from the
upgrade check changes nothing observable — the multi-project upgrade
list is under-tested in BOTH suites equally (candidate for a dedicated
test if that list matters).

## test_pytest_interpolated.py ↔ legacy `configuration.txt` (query/annotate region)

This module is pytest-only ADDED coverage of the same query/annotate
region whose mirror matrix (M1–M7, NOTES.md) ran against
test_pytest_buildout_txt.py. Here the M1–M6 mutants are re-run against
THIS module to measure its partial view. M7 (deepcopy→shallow) is the
known process-isolation equivalent mutant — not tested (see NOTES.md).

| Mutation | legacy configuration.txt | this module | sister mirror (buildout_txt) |
|---|---|---|---|
| M1 `--interpolated` returns raw | KILL | KILL | KILL |
| M2 empty-side args accepted | KILL | survive | KILL |
| M3 `a:b:c` not rejected | KILL | survive | KILL |
| M4 missing key prints None | KILL | KILL | KILL |
| M5 `annotate --interpolated` returns raw | KILL | KILL | KILL |
| M6 `value is not None` guard removed | KILL | survive | KILL |

Region-level agreement: full — every mutant dies in the legacy suite
AND in the combined pytest suite. The module-level survivals (M2, M3,
M6) are expected: this module holds only the --interpolated-focused
tests, while the error-contract tests (M2/M3) and the section-extension
test (M6) live in the mirror module test_pytest_buildout_txt.py.
Lesson: a module-scoped survival is only a divergence if NO pytest
module kills the mutant; judge regions, not files.

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
