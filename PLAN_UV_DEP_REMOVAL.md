# Plan: remove pkg_resources/setuptools from the installer=uv path

Goal: when `installer = uv`, no `pkg_resources` and no `setuptools` is
imported or provisioned by zc.buildout code; both `setuptools<82` caps
(setup.py metadata and `easy_install.py`'s `_constrained_requirement('<82',
...)`, issue #744) are dropped; the legacy doctest suite stays green with
newer setuptools and a vendored pkg_resources under BOTH `installer = pip`
and `installer = uv`. Python support is unchanged (3.9 floor kept — we do
not follow upstream's 6.0 floor-raise).

Inventory baseline (verified on devenv @ 45ba884d): hard runtime
`import setuptools` lives in `__init__.py` (warning hygiene),
`_package_index.py` (vendored setuptools 80.2.0 index, legacy pip mode
only), `easy_install.py` (legacy installer, incl. the <82 restriction),
`develop.py` (`setuptools.command.setopt`, setup.py-develop machinery),
`install_backend.py` (borrows `setuptools.archive_util` and
`setuptools.wheel.Wheel` for local file handling), `scripts.py`
(`cli.exe` from setuptools package data on Windows; `_runsetup`
template). Core `pkg_resources` sites: buildout.py (WorkingSet,
working_set.resolve, load_entry_point, iter_entry_points x2,
Requirement.parse x2, DEVELOP_DIST precedence, DistributionNotFound),
cli.py, `__init__.py` warning import, `_package_index.py` (5 refs).
No `setup_requires` anywhere.

Invariants: no user-visible behavior change except where a phase says so;
every commit green under lint, ty, complexity, pytest, `make test`,
`make test-uv`; news fragment per repo policy; author per repo policy, no
trailers; gates close at an exact head SHA; the operator lands.
Execution follows the poteto-mode discipline (pinned behavior contracts,
small verified units, delegated mechanical edits with owned review) at
every phase — stated once here, not repeated per point.

## Phase 0 — Probe (pure verification, no product change)

Done on the `uv-dep-removal` branch worktree at devenv HEAD 50ec3397,
2026-09-26. Probe: import hook + `AllowHostsPackageIndex.__init__`
counter + subprocess argv recorder, injected by a sitecustomize on
PYTHONPATH (scripts preserved in the agent workspace under
RESEARCH/uvprobe-phase0/). Lanes driven in uv mode: empty-parts,
annotate, recipe+egg from PyPI, develop egg, rerun; plus a pip-mode
recipe lane as control. Artifacts:
/tmp/verify-buildout-artifacts-phase0b-20260926-222924/.

- [x] Prove uv mode never instantiates the legacy index: zero
      `AllowHostsPackageIndex` hits in every uv lane. Probe arming
      proven separately (a direct instantiation under the probe logs).
      The pip-mode control also shows zero hits: recipe resolution on
      these lanes goes through the pip/uv subprocess, so the legacy
      index class is dormant even in pip mode. Static support
      confirmed: `_package_index` is referenced only by
      `easy_install.py` (definition at :373, instantiation via
      `_get_index` at :391) and `patches.py` (:75).
- [x] Record which `pkg_resources`/`setuptools` imports load in a
      uv-mode run: the import hook attributes each import to the
      importing zc.buildout module. Ground truth (identical in every
      lane; these are startup-time, module-top-level imports):
      `pkg_resources` is imported by `__init__`, `_package_index`,
      `buildout`, `cli`, `configsetup`, `easy_install`, `errors`,
      `install_backend`, `parts`, `patches`, `scripts` (11 modules).
      `setuptools` is pulled by `__init__` (:21, warning hygiene),
      `_package_index`, `easy_install` (:49 archive_util, :50 setopt,
      :55 wheel), `develop` (:31 setopt), and `install_backend`
      (:47 archive_util, :50 wheel). Consequence for Phase 1: the
      `__init__.py` import can only drop once `easy_install.py` and
      `develop.py` stop importing setuptools at module top in uv mode
      (buildout.py imports both unconditionally at startup).
- [x] Assert no pip subprocess fires in any uv-mode lane: zero
      `python -m pip` spawns in all uv lanes; uv lanes spawn only the
      uv binary (`uv --version`, `uv pip compile`, `uv pip install`).
      Control lane spawned exactly one `python -m pip install`,
      proving the detector fires.

## Phase 1 — Seam stdlib swaps (uv path)

Done in three units; probe lanes rerun per unit against the Phase 0
ground truth (final artifacts:
/tmp/verify-buildout-artifacts-p1u3-20260927-065026).

- [x] Replace `setuptools.archive_util.unpack_archive`
      (install_backend.py) with shutil/zipfile/tarfile handling that
      preserves current semantics (incl. the unpack_zipfile comment at
      :644).
      Done in fa2ce89d: stdlib `unpack_archive` (dir/zip/tar drivers,
      absolute/traversal entries skipped, unix modes restored,
      UserError on unrecognized) verified against the setuptools
      75.8.2 source; the `.whl` comment now points at
      `_unpack_zipfile`; four new pytests cover the seam.
- [x] Replace `setuptools.wheel.Wheel` usage (install_backend.py:671)
      with `packaging`-based name/metadata parsing (packaging is already
      a dependency).
      Done in fd497f42 by deletion instead: `unpack_wheel`,
      `BuildoutWheel` and `_maybe_copy_and_rename_wheel` had zero
      callers (the only call site was commented out, no test
      references), so 170 lines of dead code went away and no
      packaging-based port was needed. easy_install.py's remaining
      dead `Wheel` import went in c6c7f509.
- [x] Drop the bare `import setuptools` warning-hygiene import in
      `__init__.py` once nothing else pulls setuptools in uv mode.
      Deferred to Phase 3 on evidence: after units 1-3 the probe still
      attributes `setuptools` to `_package_index` (imported top-level
      by easy_install.py because `AllowHostsPackageIndex` inherits
      from `PackageIndex` at class-definition time) and to
      `__init__.py` itself. `_package_index` is repointed to the
      vendored pkg_resources in Phase 3, which is what unblocks this.
      easy_install.py and develop.py top-level setuptools imports
      (the Phase 0 precondition) are gone as of c6c7f509.
      Amendment 2026-10-03 (owner-approved unit): the Phase 3 repoint
      has landed, so the deferral precondition is met and this item
      executes now.  Discovery expanding the item: a top-level
      `import distutils.errors` is a runtime setuptools import, not a
      stdlib one — on Python 3.12+ (no stdlib distutils) it resolves
      through setuptools' `_distutils_hack` meta-finder, which imports
      setuptools itself, so the pull is invisible to a grep for
      `setuptools`.  Proven standalone on the pinned 3.12/75.8.2 env:
      a fresh interpreter running only `import distutils.errors` ends
      with `setuptools` in sys.modules.  Three top-level sites keep
      setuptools in every startup: buildout.py:21 is dead (zero other
      distutils refs in the file) and is deleted; easy_install.py:25
      has one real use (:1358, legacy-only setup-script discovery) and
      moves inside `_unpack_dist_for_build`; cli.py:29 has one real
      use (:274, the isinstance in the failure reporter) and moves
      inside `_handle_buildout_error`; then `__init__.py:26` drops.
      pep425tags.py's top-level `import distutils.util` is not a
      startup puller (configsetup.py imports pep425tags lazily) and
      stays.  Accepted edge: a FAILING uv-mode run imports setuptools
      inside the error reporter just before exit (the lazy cli.py
      import fires on the failure path); removing that would re-type
      the raised error and change legacy-mode-visible behavior, which
      the invariants forbid.  Contract: a subprocess pytest asserting
      `setuptools` not in sys.modules after `import
      zc.buildout.buildout`, landed failing first and turned green by
      the removals.
      Done in 92d82be3 (contract pinned failing first in 28d6818f;
      baseline refreshed for line drift in f5e5416d).  Verified on
      f5e5416d: contract pytest green (red reproduced against the
      28d6818f tree via git archive), make lint / make complexity
      (931 blocks within budget) / make typecheck (ty: all checks
      passed) / make pytest (820 passed) green, make test 661 tests
      0 failures; the acceptance probe prints False for `setuptools`
      in sys.modules after `import zc.buildout.buildout`
      (`pkg_resources` True, the vendored shim, as designed).
- [x] Gate: unit ladder green; live lanes regression/develop/uv-resolve
      identical vs pre-phase base.
      Per unit: lint, ty, typecheck-any, complexity and pytest green.
      `make test` 656/656 and `make test-uv` 652/652 on each unit
      commit, last on c6c7f509. Probe lanes show the uv-mode import
      set shrinking by exactly the predicted lines with zero
      additions, uv-only spawns, and the legacy index never
      instantiated.

## Phase 2 — Core pkg_resources layer (both modes benefit)

- [x] Port the ~10 core call sites to stdlib/packaging equivalents:
      `Requirement.parse` -> `packaging.Requirement`;
      `load_entry_point`/`iter_entry_points` -> `importlib.metadata.entry_points`;
      `WorkingSet`/`working_set.resolve` -> `importlib.metadata.distributions`
      plus the dist model the uv seam already uses;
      `DistributionNotFound` -> `importlib.metadata.PackageNotFoundError`;
      `DEVELOP_DIST` precedence -> our own editable detection.
- [x] Keep the legacy suite's monkeypatch points working (facade or
      shim where the suite patches these names).
- [x] Gate: full unit ladder + ten-lane live harness, both modes.

## Phase 3 — Legacy suite on newer setuptools via vendored pkg_resources

The compatibility shim that lets the <82 caps die while legacy pip mode
keeps working, and that keeps the legacy doctest corpus green on newer
setuptools and Python.

- [x] Vendor pkg_resources (upstream's approach in #751, a84d9c5b — take
      it per se if it applies cleanly) and repoint legacy-mode imports
      (easy_install.py, _package_index.py, scripts.py resource access)
      to the vendored copy.
- [x] Drop the `setuptools<82` cap in setup.py and the `<82` restriction
      in easy_install.py (legacy path keeps working through the vendored
      pkg_resources, not through setuptools' copy).
- [x] Legacy suite proven with newer setuptools: keep the hermetic seed
      floor (testing.py, currently 75.8.2) for reproducibility AND add a
      setuptools-latest leg; `make test` and `make test-uv` both green on
      it. This is the acceptance test that the vendoring, not the cap,
      is what keeps legacy alive.
- [ ] Make pip legacy-only: drop `'pip'` from unconditional
      install_requires (setup.py); pip becomes the opt-in
      `zc.buildout[pip]` extra and pip mode fails fast with a clear
      error when pip is missing (owner decision 2026-09-30: B+C —
      explicit error plus extra, no auto-provisioning).
      Test scaffolding keeps seeding it. User-visible for anyone
      relying on zc.buildout to pull pip in — news fragment calls it
      out. After this, uv mode has no pip dependency at all.
- [ ] Keep the Python window 3.9-3.14; add a 3.15 leg when the nix
      toolchain carries it (upstream #765 in the same vein).

## Phase 4 — Script stragglers (uv path)

- [ ] ~~Windows `cli.exe`~~ **DEFERRED (owner decision 2026-09-30).**
      Verified empirically: every setuptools from 75.8.2 through 84.0.0
      still ships all eight launcher binaries (cli/gui × 32/64/arm64),
      and setuptools' NEWS records no removal or deprecation. The
      premise was defensive. Re-open only if upstream announces a
      removal — the floating setuptools-latest canary legs would show
      it first. Original options preserved for that day: vendor the
      static launcher binaries once (console), and declare gui_scripts
      unsupported (our generator only ever produced console launchers).
- [x] Retire or rewrite the `_runsetup` template (scripts.py:593) so
      generated scripts never `import setuptools` in uv mode.
      Done in 7a60669d (contract pinned red) and 0ff84026 (option B+C):
      scripts.py gained `_runsetup_template_uv` — the same template
      without the `import os, setuptools` line — and
      `_runsetup_template_for`, picked by installer mode at
      easy_install's single assembly site. Pip/legacy mode is
      bit-identical. Contract: subprocess template assembly per mode
      (uv: no setuptools import; pip: still pre-imports). No doc-leg
      adjustment was needed: with setuptools still installed in the
      test environments, its vendored distutils keeps resolving
      `bdist_egg` for distutils-style setup.py files, so
      runsetup.txt/setup.txt/repeatable.txt/windows.txt pass unchanged
      in both lanes. The accepted trade-off (distutils-style setup.py
      leaning on the pre-import loses bdist_egg) only materializes
      once setuptools stops being installed — a later phase.
      Runtime evidence: a real `bin/buildout setup` uv-mode run of a
      setup.py asserting `'setuptools' not in sys.modules` printed
      `SETUPTOOLS_PREIMPORTED: False` (pip-mode control: `True`) and
      produced the sdist.

## Phase 5 — Develop eggs (frontier, may be split out)

- [ ] Route develop through PEP 660 editable installs via uv
      (`uv pip install -e`), building on the editable/egg-link/pth
      handling install_backend.py already maps for setuptools 79/80+.
      Retire the setup.py-develop fallback in develop.py for uv mode.
      Rhymes with upstream #746; port its zc.recipe.egg half if it
      applies.

## Close the program

- [ ] Root-cause and fix the `test_runsetup` isolation flakiness (fails
      standalone, green in full xdist runs; pre-existing on devenv —
      proven by stash on e4de821f and 3fef1678). Every phase gates on
      the legacy suites, so suite trust is program-critical.
- [ ] `python -c "import zc.buildout.buildout"` in a uv-mode hermetic
      env loads neither pkg_resources nor setuptools (import-hook proof).
- [ ] setup.py has no setuptools upper bound; easy_install.py has no
      <82 clause.
- [ ] Legacy suite green with setuptools-latest under both installer
      modes, Python 3.9 and newest supported.
- [ ] Every box above ticked with evidence (paths, SHAs, logs); operator
      lands each phase on devenv.
