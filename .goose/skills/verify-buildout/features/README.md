# Buildout verification map

This directory is the maintained source for verifying the user-facing
behavior of zc.buildout from this checkout. Read this index before
driving, then use the matching feature file as the recipe.

## Baseline preconditions

- Run the doctor first:
  `.goose/skills/verify-buildout/helpers/doctor.sh` — all OK.
- Set `REPO` to the checkout root (this skill lives at
  `$REPO/.goose/skills/verify-buildout/`). The app under test is the
  checkout's own `$REPO/bin/buildout` — a dev install of the current
  source tree, whatever branch is checked out.
- `export PYTHONWARNINGS=ignore` for every command (pkg_resources
  deprecation noise otherwise floods transcripts).
- Every drive gets its own throwaway project dir:
  `D=$(mktemp -d /tmp/verify-buildout.XXXXXX)` — never drive in the
  repo root (it rewrites `.installed.cfg`, `parts/`, `eggs/`).
- Evidence goes to a dir that survives cleanup:
  `ART=/tmp/verify-buildout-artifacts-$(date +%Y%m%d-%H%M%S)`.

## Driving conventions

- Treat every command as literal. Keep quoted names and flags unchanged.
- Record the feature ID, `git rev-parse HEAD`, command, exit code, and
  full transcript per drive.
- Run results are verified on disk (`.installed.cfg`, `bin/` scripts).
  `query`/`annotate` are a separate, read-only axis: they explore the
  configuration files as composed (`extends` chain, assignments,
  defaults) — not the result of a run.
- Restore nothing — drives are disposable by construction — but retain
  all proof artifacts during cleanup.

## Proof and skip reporting

- CLI proof includes the command, stdout, stderr, and exit code.
- Mutation proof is on-disk side effects (`.installed.cfg`, `bin/`
  scripts). Configuration-composition proof is `query`/`annotate`
  output — the two answer different questions; never substitute one
  for the other.
- A networked drive that fails on a fetch is NOT a buildout failure:
  report it as environment-limited, attempt the hermetic tier, and say
  so explicitly. Do not report a networked path as verified through a
  hermetic run.

## Tiers

- **Hermetic** (no network): install-and-inspect, configure-and-substitute,
  rerun-modes.
- **Networked** (PyPI or warm pip cache): scaffolding (init/bootstrap),
  the real part install inside install-and-inspect.
- **Suites**: repo-test-suites (`make test`, `make pytest`).

## Features

- [Install and inspect a project](./install-and-inspect.md) — the core
  loop: config in, directories and scripts out, composed configuration
  explorable.
- [Configure and substitute](./configure-and-substitute.md) — INI
  composition, `${section:option}` substitution, command-line
  assignments, `query`/`annotate`.
- [Rerun and update modes](./rerun-modes.md) — second-run behavior,
  `-N` non-newest mode, `-U` user-defaults isolation.
- [Project scaffolding](./scaffolding.md) — `buildout init` /
  `bootstrap` creating a new project (networked).
- [Repo test suites](./repo-test-suites.md) — `make test` (legacy
  doctest suite) and `make pytest` (ported pytest suite) as the deep
  behavior proof.
