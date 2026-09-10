# Project scaffolding (init / bootstrap)

`buildout init [requirements]` creates a minimal `buildout.cfg` in an
empty directory and bootstraps a project-local `bin/buildout`;
`buildout bootstrap` does the bootstrap half for an existing config.
This is how a user starts a brand-new project.

## Sub-features

- `init-empty` — `init` in an empty dir creates `buildout.cfg` and a
  project-local `bin/buildout`.
- `init-requirements` — `init bobo` generates a config with an
  interpreter part requiring `bobo`.
- `bootstrap-existing` — `bootstrap` on a hand-written config creates
  the local script without touching the config.

## How to get to it (user POV)

- In an empty directory: `/path/to/checkout/bin/buildout init`.
- With requirements: `/path/to/checkout/bin/buildout init bobo`.
- With an existing `buildout.cfg`: `/path/to/checkout/bin/buildout bootstrap`.

## Driving it with shell

Preconditions:

- Doctor all-OK; `PYTHONWARNINGS=ignore`; fresh empty `$D`; `B` set.
  **This feature is networked**: init/bootstrap install buildout and
  setuptools into the new project (PyPI or warm pip cache).

- **Init.** `cd "$D" && "$B" init 2>&1 | tee "$ART/init.log"`.
  Exit 0. Assert: `test -f buildout.cfg && test -x bin/buildout`.
  `cat buildout.cfg` into the transcript — it must contain a
  `[buildout]` section.
- **Drive the scaffolded project.** `./bin/buildout 2>&1 | tee -a "$ART/init.log"`
  (the LOCAL script now, not the checkout's). Exit 0 — the scaffold is
  self-sufficient.
- **Init with requirements.** Second dir `$D2`:
  `"$B" init bobo 2>&1 | tee "$ART/init-requirements.log"`, then
  `grep -n bobo buildout.cfg` — the generated config mentions `bobo`
  in an interpreter part.
- **Bootstrap only.** Third dir `$D3` with a hand-written
  `printf '[buildout]\nparts =\n' > buildout.cfg`:
  `"$B" bootstrap 2>&1 | tee "$ART/bootstrap.log"`. Exit 0;
  `test -x bin/buildout`; `buildout.cfg` byte-identical before/after
  (`cp buildout.cfg "$ART/cfg.before"` first, then `cmp`).

## Gotchas

- Slowest feature: init/bootstrap create a fresh environment per
  project. Budget a minute or two per drive; do not interrupt —
  half-created `bin/` dirs assert fine as failures if you record the
  transcript.
- On macOS there is no `timeout` command; use plain invocation and let
  the transcript show duration.
- If PyPI is unreachable every sub-feature fails on the fetch —
  report environment-limited, keep transcripts, and do not retry in a
  loop.
- The scaffolded `bin/buildout` is independent of the checkout: proof
  of `init` must drive the LOCAL `./bin/buildout`, not `$B`, or you
  have only proven the checkout again.
