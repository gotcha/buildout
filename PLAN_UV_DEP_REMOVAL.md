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

## Phase 0 — Probe (pure verification, no product change)

- [ ] Prove uv mode never instantiates the legacy index: instrument
      `AllowHostsPackageIndex.__init__` (or an import-time counter) and
      drive the ten-lane live harness in uv mode; expected: zero hits.
      Static support: `_package_index` is only referenced by
      `easy_install.py` and `patches.py`.
- [ ] Record which `pkg_resources`/`setuptools` imports load in a uv-mode
      run (`python -X importtime` or an import hook on a representative
      lane). This is the removal checklist ground truth.
- [ ] Assert no pip subprocess fires in any uv-mode lane (uv mode must
      use only the uv binary; install_backend.py's pip branch stays
      unreachable).

## Phase 1 — Seam stdlib swaps (uv path)

- [ ] Replace `setuptools.archive_util.unpack_archive`
      (install_backend.py) with shutil/zipfile/tarfile handling that
      preserves current semantics (incl. the unpack_zipfile comment at
      :644).
- [ ] Replace `setuptools.wheel.Wheel` usage (install_backend.py:671)
      with `packaging`-based name/metadata parsing (packaging is already
      a dependency).
- [ ] Drop the bare `import setuptools` warning-hygiene import in
      `__init__.py` once nothing else pulls setuptools in uv mode.
- [ ] Gate: unit ladder green; live lanes regression/develop/uv-resolve
      identical vs pre-phase base.

## Phase 2 — Core pkg_resources layer (both modes benefit)

- [ ] Port the ~10 core call sites to stdlib/packaging equivalents:
      `Requirement.parse` -> `packaging.Requirement`;
      `load_entry_point`/`iter_entry_points` -> `importlib.metadata.entry_points`;
      `WorkingSet`/`working_set.resolve` -> `importlib.metadata.distributions`
      plus the dist model the uv seam already uses;
      `DistributionNotFound` -> `importlib.metadata.PackageNotFoundError`;
      `DEVELOP_DIST` precedence -> our own editable detection.
- [ ] Keep the legacy suite's monkeypatch points working (facade or
      shim where the suite patches these names).
- [ ] Gate: full unit ladder + ten-lane live harness, both modes.

## Phase 3 — Legacy suite on newer setuptools via vendored pkg_resources

The compatibility shim that lets the <82 caps die while legacy pip mode
keeps working, and that keeps the legacy doctest corpus green on newer
setuptools and Python.

- [ ] Vendor pkg_resources (upstream's approach in #751, a84d9c5b — take
      it per se if it applies cleanly) and repoint legacy-mode imports
      (easy_install.py, _package_index.py, scripts.py resource access)
      to the vendored copy.
- [ ] Drop the `setuptools<82` cap in setup.py and the `<82` restriction
      in easy_install.py (legacy path keeps working through the vendored
      pkg_resources, not through setuptools' copy).
- [ ] Legacy suite proven with newer setuptools: keep the hermetic seed
      floor (testing.py, currently 75.8.2) for reproducibility AND add a
      setuptools-latest leg; `make test` and `make test-uv` both green on
      it. This is the acceptance test that the vendoring, not the cap,
      is what keeps legacy alive.
- [ ] Make pip legacy-only: drop `'pip'` from unconditional
      install_requires (setup.py:53); pip mode provisions it itself,
      test scaffolding keeps seeding it. User-visible for anyone
      relying on zc.buildout to pull pip in — news fragment calls it
      out. After this, uv mode has no pip dependency at all.
- [ ] Keep the Python window 3.9-3.14; add a 3.15 leg when the nix
      toolchain carries it (upstream #765 in the same vein).

## Phase 4 — Script stragglers (uv path)

- [ ] Windows `cli.exe`: vendor the static launcher binary once, or
      declare gui-script support dropped (operator decision — the only
      intentional user-visible break candidate in this plan).
- [ ] Retire or rewrite the `_runsetup` template (scripts.py:593) so
      generated scripts never `import setuptools` in uv mode.

## Phase 5 — Develop eggs (frontier, may be split out)

- [ ] Route develop through PEP 660 editable installs via uv
      (`uv pip install -e`), building on the editable/egg-link/pth
      handling install_backend.py already maps for setuptools 79/80+.
      Retire the setup.py-develop fallback in develop.py for uv mode.
      Rhymes with upstream #746; port its zc.recipe.egg half if it
      applies.

## Close the program

- [ ] `python -c "import zc.buildout.buildout"` in a uv-mode hermetic
      env loads neither pkg_resources nor setuptools (import-hook proof).
- [ ] setup.py has no setuptools upper bound; easy_install.py has no
      <82 clause.
- [ ] Legacy suite green with setuptools-latest under both installer
      modes, Python 3.9 and newest supported.
- [ ] Every box above ticked with evidence (paths, SHAs, logs); operator
      lands each phase on devenv.
