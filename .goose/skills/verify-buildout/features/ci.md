# CI workflows: verify a change to `.github/workflows/`

Verifying a CI change means proving the workflow will do on the runner
what it does for a developer locally. No local suite exercises CI yaml —
the legacy suite is blind to it (see the develop-buildout skill) — so
the proof ladder is different: parse, run the changed commands locally
inside the devenv, then read the pushed-branch CI run.

## The provisioning contract

GitHub actions only bootstrap the repo's own environment. The allowed
actions are `actions/checkout` and the repo-owned composite action
`.github/actions/devenv-setup` (Nix + the devenv CLI, built from the
nixpkgs revision pinned in `devenv.lock`). Everything else — Python
3.9–3.14, uv, ruff, ty, make — comes from the devenv, so CI and a local
`devenv shell` agree by construction.

Per-job commands have the shape:

```sh
devenv shell \
  --option languages.python.version:string "<python-version>" \
  -- make [pytest|test-small|lint|typecheck|-f .github/workflows/Makefile-scripts ...]
```

Matrix values that the repo bootstrap understands ride as environment
variables (`SETUPTOOLS_VERSION`, `PIP_VERSION`), exactly as the
verify-buildout launch does locally. `PYTHON_VERSION` is NOT passed by
the workflow: the devenv exports it from the `--option` override.

The single sanctioned exception is the Windows job: Nix does not run on
Windows runners, so it keeps `actions/setup-python` — but it still
drives the same repo-owned entry points (`make`, `make pytest`).

## Proof ladder for a CI change

1. **Parse.** Every changed yaml file parses:
   `python3 -c "import yaml; yaml.safe_load(open('<file>'))"`.
2. **Local command proof.** Run each changed job command locally,
   inside the devenv, from the checkout root — e.g.
   `devenv shell -- make lint`,
   `devenv shell -- make test-small`,
   `devenv shell -- make -f .github/workflows/Makefile-scripts sandbox/bin/buildout`.
   Record command, exit code, transcript tail, and
   `git rev-parse HEAD`. This proves the repo-owned entry points work
   under `devenv shell` one-shot invocation — the exact shape CI uses.
3. **Runner proof.** Push the branch (to the fork remote only — never
   the upstream org repo) and read the CI run:
   `gh run list --repo <owner>/<repo> --branch <branch>`, then
   `gh run view <id> --log-failed` for failures. A green run on the
   branch is the only proof the runner environment accepts the change;
   local proof cannot see runner-specific gaps (missing jq, Nix install
   time, cold binary caches).
4. **Cost evidence.** Note the devenv/Nix bootstrap time the run adds
   per job (the `devenv-setup` step durations in the run log). Cold
   binary caches make the first run of a job the worst case.

## Gotchas

- `devenv shell -- <cmd>` runs the command one-shot and still prints
  the `enterShell` banner — harmless noise in CI logs, do not mistake
  it for job output.
- The devenv python has no pip (nixpkgs pythons disable ensurepip) and
  no virtualenv. Anything that used `pip install virtualenv` against
  the ambient python must go through the devenv's uv instead —
  `uv venv --seed --python "$(command -v python)"` (the explicit path
  stops uv from substituting a uv-managed interpreter).
- YAML parse checks do not validate GitHub's schema (action versions,
  `needs:` graph). Runner proof (step 3) is where those surface.
