# Plan: remove pkg_resources/setuptools from the installer=uv path

Goal: when `installer = uv`, no `pkg_resources` and no `setuptools` is
imported or provisioned by zc.buildout code; both `setuptools<82` caps
(setup.py metadata and `easy_install.py`'s `_constrained_requirement('<82',
...)`, issue #744) are dropped; the legacy doctest suite stays green with
newer setuptools and a vendored pkg_resources under BOTH `installer = pip`
and `installer = uv`. The Python floor moves to 3.10 (port-plan decision
D1, 2026-10-09: we follow upstream's 6.0 floor-raise after all, 3.9 is
EOL).

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
      :644 — pin verified imprecise at audit 2026-10-09: the `.whl`
      comment lives at :840 and `_unpack_zipfile` at :775 of the
      current tree; substance verified independently).
      Done in fa2ce89d: stdlib `unpack_archive` (dir/zip/tar drivers,
      absolute/traversal entries skipped, unix modes restored,
      UserError on unrecognized) verified against the setuptools
      75.8.2 source; the `.whl` comment now points at
      `_unpack_zipfile`; four new pytests cover the seam.
- [x] Replace `setuptools.wheel.Wheel` usage (install_backend.py —
      the :671 pin was stale; the actual era site was :644, and the
      names are gone from the current tree entirely)
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
      Evidence (annotated at close-out audit 2026-10-09): unit commits
      a391db18, 1a1f7cf4, 8ddbf811, a8849112, 030d558d, 179e3fc1,
      95733941, 801b97a3 in-branch; src/zc/buildout/_workingset.py
      carries the dist model; easy_install.py's remaining pkg_resources
      references are function-local only (zero top-level imports).
- [x] Keep the legacy suite's monkeypatch points working (facade or
      shim where the suite patches these names).
      Evidence (annotated at close-out audit 2026-10-09): the
      _workingset facade bridges the patched names; suite greens
      corroborated per unit in the work log (PHASE_*_EVIDENCE).
- [x] Gate: full unit ladder + ten-lane live harness, both modes.
      Evidence (annotated at close-out audit 2026-10-09): da9fff8c,
      f7c46e7a in-branch; dagger uv lanes 21/21 + static tier 4/4
      recorded in the work log; era suites 656/656 + 652/652 per unit.

## Phase 3 — Legacy suite on newer setuptools via vendored pkg_resources

The compatibility shim that lets the <82 caps die while legacy pip mode
keeps working, and that keeps the legacy doctest corpus green on newer
setuptools and Python.

- [x] Vendor pkg_resources (upstream's approach in #751, a84d9c5b — take
      it per se if it applies cleanly) and repoint legacy-mode imports
      (easy_install.py, _package_index.py, scripts.py resource access)
      to the vendored copy.
      Evidence (annotated at close-out audit 2026-10-09): in-branch
      72ce3219; upstream commit a84d9c5b exists as a local object;
      vendored tree at src/zc/buildout/_vendor/pkg_resources/; the
      meta_path bridge (zc/buildout/__init__.py:95-114) resolves
      `pkg_resources` to the vendored copy — proven import-clean by
      the close-item-2 hermetic probe (re-executed green at audit).
- [x] Drop the `setuptools<82` cap in setup.py and the `<82` restriction
      in easy_install.py (legacy path keeps working through the vendored
      pkg_resources, not through setuptools' copy).
      Evidence (annotated at close-out audit 2026-10-09): in-branch
      469e169d; setup.py:56 `setuptools>=61.0.0` is the only setuptools
      specifier; `easy_install.py` has zero `82` hits (grep exit 1).
- [x] Legacy suite proven with newer setuptools: keep the hermetic seed
      floor (testing.py, currently 75.8.2) for reproducibility AND add a
      setuptools-latest leg; `make test` and `make test-uv` both green on
      it. This is the acceptance test that the vendoring, not the cap,
      is what keeps legacy alive.
      Evidence (annotated at close-out audit 2026-10-09): in-branch
      e8e33677 + 2224e92f; floating setuptools leg carries
      `setuptools=""` in dagger/src/buildout_ci/jobs.py (:91, :203);
      the full four-leg matrix landed under close-the-program item 4
      (below) with all greens.
- [x] Make pip legacy-only: drop `'pip'` from unconditional
      install_requires (setup.py); pip becomes the opt-in
      `zc.buildout[pip]` extra and pip mode fails fast with a clear
      error when pip is missing (owner decision 2026-09-30: B+C —
      explicit error plus extra, no auto-provisioning).
      Test scaffolding keeps seeding it. User-visible for anyone
      relying on zc.buildout to pull pip in — news fragment calls it
      out. After this, uv mode has no pip dependency at all.
      Done 2026-09-30 (ticked at close-out audit 2026-10-09 — the work
      landed on time; the box was a tick-sync miss): in-branch
      967bf1f7 "Phase 3 item 4: make pip an opt-in extra";
      setup.py:58-61 comment + :79 `"pip": ["pip"]` extra;
      news/+pip-extra.breaking.rst.
- [ ] Keep the Python window 3.10-3.14; add a 3.15 leg when the nix
      toolchain carries it (upstream #765 in the same vein). M9 fold
      (upstream-port unit 4.3, 2026-10-10): the nix-gated leg stays the
      single 3.15 effort; when it lands it carries the M12 pins as of
      that date (setuptools-latest in the python jobs, encoded 84.0.0
      today; pip-latest 26.2.1 where pip legs apply), matching upstream's
      shape of one python job cell at the newest setuptools. No separate
      M9 leg is created in CI now: plan-doc item only.

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

- [x] Route develop through PEP 660 editable installs via uv
      (`uv pip install -e`), building on the editable/egg-link/pth
      handling install_backend.py already maps for setuptools 79/80+.
      Retire the setup.py-develop fallback in develop.py for uv mode.
      Rhymes with upstream #746; port its zc.recipe.egg half if it
      applies.

      Done 2026-10-09 (f2bdda07..595a6d13).  The "route" and "retire"
      clauses were already absorbed by earlier branch units (develop
      already went through `uv pip install -e`; no setup.py-develop
      code remained).  The shipped work is the #746-shaped gap the
      sleuth map exposed: pyproject-only (PEP 660, e.g. hatchling)
      develop packages left no metadata in the checkout, so the
      fabricated egg-link resolved to nothing in BOTH installer modes.
      The editable install's .dist-info and plain-path .pth are now
      kept in develop-eggs (conditional on a metadata-less checkout,
      so setuptools layouts are bit-identical), scripts resolve the
      .pth's plain path, and the buildout process site-processes
      develop-eggs so recipes can entry-point-import from them.
      Import-hook-only editables without checkout metadata are a
      documented non-goal.  The zc.recipe.egg half of #746 needed no
      port: the conditional copy provoked no listing churn there.

## Close the program

- [x] Root-cause and fix the `test_runsetup` isolation flakiness (fails
      standalone, green in full xdist runs; pre-existing on devenv —
      proven by stash on e4de821f and 3fef1678). Every phase gates on
      the legacy suites, so suite trust is program-critical.

      Done 2026-10-09 (047ef10a).  Root cause was never isolation:
      every Makefile gate sets PYTHONWARNINGS=ignore while bare
      invocations do not, and testing.system() forwarded the ambient
      environment — so ad-hoc runs leaked two warning banners (the
      vendored pkg_resources deprecation, the setuptools 75.8.2
      setup.py banner) into compared output.  A/B runs ruled out
      xdist, test ordering and egg-cache drift; the minimal enabler
      was the env var alone.  Fix is one seam: system() defaults
      PYTHONWARNINGS to ignore unless the caller set it.  Also
      retires the bad_py / show_who_requires watch items (same
      family, verified ad-hoc green).  Full ladder green on the
      final tree (lint/typecheck/typecheck-any/complexity, pytest
      837, test 661/661, test-uv 657/657).
- [x] `python -c "import zc.buildout.buildout"` in a uv-mode hermetic
      env loads neither pkg_resources nor setuptools (import-hook proof).

      Done 2026-10-09 (7e3b5aa4 RED contract, 3f03d923 implementation).
      The eager vendored-pkg_resources aliasing in zc/buildout/__init__.py
      is replaced by a meta_path bridge serving the vendored copy on
      demand: import-hooks are never consulted for pre-imported copies
      (module identity under issue #685 preserved), and nothing of the
      setuptools/pkg_resources/vendored lineages loads on a plain
      import.  The warning filters and the Requirement/WorkingSet
      patches move to bridge-fire time, bit-identical to legacy timing.
      Proof is import-hook based, not grep: a raising meta_path blocker
      in a hermetic uv env (Python 3.13, buildout installed from the
      checkout, no setuptools import allowed) prints PROBE GREEN, and
      test_no_setuptools_or_pkg_resources_import pins the same contract
      in-repo.  Full ladder green on the final tree:
      lint/typecheck/typecheck-any/complexity, pytest 847 passed,
      test 661/661, test-uv 657/657.
- [x] setup.py has no setuptools upper bound; easy_install.py has no
      <82 clause.

      Done 2026-10-09 (verify tick — earlier phases removed both).
      Evidence: setup.py:56 carries the only packaging specifier,
      'setuptools>=61.0.0'; a first-party-wide scan for 'setuptools <'
      finds only comments describing the issue #685 keep-existing-copy
      behavior; and '82' has zero hits in easy_install.py (grep exit 1
      at 3f03d923).
- [x] Legacy suite green with setuptools-latest under both installer
      modes, Python 3.9 and newest supported.

      Done 2026-10-09 (four-leg matrix, all green at 8ee14d9b).
      'Setuptools-latest' resolves per cell by requires_python: py3.9
      legs carry 82.0.1 (latest line for 3.9 — 84.0.0 needs >=3.10),
      py3.14 legs carry 84.0.0. Legs (each via Makefile PYTHON_VERSION
      knob, logs in ~/.buzz/.scratch/close-item4/):
      `make test PYTHON_VERSION=3.9` 661/661, 0F/0E (leg-39-pip.log);
      `make test-uv PYTHON_VERSION=3.9` 657/657, 0F/0E (leg-39-uv.log);
      `make test PYTHON_VERSION=3.14` 661/661, 0F/0E (leg-314-pip.log);
      `make test-uv PYTHON_VERSION=3.14` 657/657, 0F/0E
      (leg-314-uv.log). The first py3.9 leg's 3F+6E were root-caused by
      gt-sleuth to one staging bug (an intermediate zc.recipe.egg=4.0.0
      pin excluded the 4.0.1.dev0 develop checkout, so the index egg
      was fetched and globbed — both the 3 doctest failures and the 6
      fixture-wheel setUp errors follow from that); the fix is the
      staging commited as 8ee14d9b (zc.recipe.egg deliberately
      unpinned; py<3.10 runner tools pinned). No py3.9 + setuptools-82
      branch incompatibility: the same cell builds the fixture wheel
      cleanly when resolution points at the develop checkout.
- [ ] Every box above ticked with evidence (paths, SHAs, logs); operator
      lands each phase on devenv.

### Closing evidence packet (close-out audit, 2026-10-09)

Audit: read-only pass over every checkbox vs. disk and git at
6099ef60 (full dated record in
WORK_LOGS/UV_DEP_REMOVAL_2026-09-26.md, section
`2026-10-09 (gt-sleuth) — item 5 closing audit`). Verdict: every
claim in this plan re-verified positively; the hygiene misses found
(a landed-but-unticked Phase-3 box, six bare ticks, two stale line
pins) were repaired in the same pass. The hermetic import probe was
re-executed against the exactly-current source (PROBE GREEN, exit 0).

History: program range is `daa3d91f..6099ef60` (51 commits). The
2026-10-09 rebase onto 5.3.x is proven content-preserving — all 27
pre-rebase commits map 1:1 via range-diff (the `!` inter-diffs are
complexity-baseline line-pin drift plus three context-only hunks),
the two patch-id spot-checks MATCH, and the dropped cherry-pick trio
is patch-id-identical to its 5.3.x originals. Pre-rebase SHAs cited
above (e.g. fa2ce89d, fd497f42, cc1b8163) exist as git objects with
verified in-branch equivalents (see the audit map).

Ladder (final-tree results): static tier green per gated unit;
pytest 847 passed at item-2 head; `make test` 661/661 and
`make test-uv` 657/657 at items 1-2 and as the item-4 legs
(py3.9 pip 661 0F/0E, py3.9 uv 657 0F/0E, py3.14 pip 661 0F/0E,
py3.14 uv 657 0F/0E — logs logged beside the legs); hermetic probe
green. News: 32 program fragments under news/.

Landing note: pushing `uv-dep-removal` to the fork's existing branch
tip (07d4382c) is non-fast-forward because of the rebase — the
landing route (force-with-lease over the pre-rebase shadows vs.
merge onto devenv) is the operator's call. Tick this last box when
landed.
