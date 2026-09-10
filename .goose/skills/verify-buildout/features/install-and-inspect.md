# Install and inspect a project

The core buildout loop: a user writes `buildout.cfg`, runs
`bin/buildout`, and gets the project skeleton (`bin/`, `parts/`,
`eggs/`, `develop-eggs/`), installed parts with generated scripts, and
`.installed.cfg` recording what was installed. The configuration as
composed from the files is then explorable through `query` and
`annotate` — they read the configuration, not the run's results.

## Sub-features

- `install-empty` — hermetic: empty `parts =` creates the four
  directories, exit 0, and (expectedly) no `.installed.cfg`.
- `install-part` — networked: a real part with `zc.recipe.egg` installs
  an egg and generates scripts in `bin/`.
- `inspect-state` — `query section:option` and `annotate` explore the
  composed configuration (what the files say, where each value came
  from) without installing anything new.

## How to get to it (user POV)

- Run `bin/buildout` (or `bin/buildout install`) in a directory
  containing `buildout.cfg`.
- Run `bin/buildout query section:option` to print one value.
- Run `bin/buildout annotate` to print all sections with value origins.

## Driving it with shell

Preconditions:

- Doctor all-OK; `PYTHONWARNINGS=ignore`; fresh `$D` project dir;
  evidence dir `$ART`. `REPO` set to the checkout root, `B="$REPO/bin/buildout"`.

- **Empty install.** In `$D`: `printf '[buildout]\nparts =\n' > buildout.cfg`,
  then `"$B" 2>&1 | tee "$ART/install-empty.log"`. Exit code `0`;
  output lists `Creating directory ...` for `bin`, `parts`,
  `develop-eggs` (eggs/v5 may already exist from earlier probes).
  `ls` shows `bin`, `develop-eggs`, `eggs`, `parts`, `buildout.cfg`.
  Assert: `test ! -f .installed.cfg` — with zero parts none is written.
- **Explore the configuration.** `"$B" query buildout:directory`
  prints `$D`.
  `"$B" annotate | head -20` shows `[buildout]` options each followed
  by an origin line (`DEFAULT_VALUE` etc.). Both exit 0.
- **Real part install (networked).** Write:

  ```ini
  [buildout]
  parts = py
  develop = <REPO>/zc.recipe.egg_

  [py]
  recipe = zc.recipe.egg
  eggs = bobo
  interpreter = py
  ```

  Run `"$B" 2>&1 | tee "$ART/install-part.log"`. Exit `0`; transcript
  ends with `Generated script '.../bin/bobo'` and
  `Generated interpreter '.../bin/py'`. Side effects: `.installed.cfg`
  exists and has a `[py]` section with `__buildout_installed__`;
  `ls bin/` shows `bobo` and `py`; `ls eggs/v5/` shows a `bobo` egg.
- **End-to-end use.** `./bin/py -c "import bobo; print('bobo OK')"`
  prints `bobo OK` — the generated interpreter really imports the
  installed egg. Capture into `$ART/install-part-use.log`.

## Gotchas

- `install-part` needs PyPI (or a warm pip cache): `bobo`'s dependency
  `WebOb` is downloaded. A fetch failure means environment-limited,
  not app-broken — fall back to `install-empty` and report as such.
- `develop =` must point at the checkout's `zc.recipe.egg_` (trailing
  underscore is real — the directory is named that way). In the config
  block above, replace `<REPO>` with the actual checkout root when
  writing the file — INI has no variable expansion of its own.
- Even `query` creates `eggs/v5/` in the project dir as a side effect;
  "read-only" means it installs nothing, not zero disk writes. And it
  reads the configuration files as composed — never the results of a
  run.
- Empty-parts runs write no `.installed.cfg`; only a run that installs
  at least one part does. Don't assert its presence for `install-empty`.
- Never run these drives in the repo root — `bin/buildout` there
  rewrites the checkout's own `.installed.cfg`/`parts/`/`eggs/`.
