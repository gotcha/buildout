---
name: dagger
description: Operate this checkout's local dagger CI mirror — engine lifecycle on the devenv podman machine, the remediation ladder when the engine wedges, and run discipline (frozen tree, foreground, flake re-runs). Use when running dagger families or single cells locally, when a dagger call cannot connect or dies mid-run, or when a result must match CI.
---

# Dagger

Scope: this skill covers *operating* the local engine and its runs.
Changing the module (Job table, cells, cache design) is covered by
develop-buildout's "Dagger CI module" section; choosing which
verification axis proves what is covered by verify-buildout.

## Invocation

- The `dagger` CLI is not on the ambient PATH; the devenv provides it
  and wires it to the engine. Invoke from the checkout root:
  `devenv shell -- dagger ...`. The shell exports
  `_EXPERIMENTAL_DAGGER_RUNNER_HOST=container+podman://devenv-dagger`.
  Bare `podman` outside the shell can hit a *different* default
  connection (observed: a stopped `podman-machine-default` while the
  engine lives on `devenv`) — name it explicitly:
  `podman --connection devenv ...`.
- `dagger call families` lists the families; the cells are the Job
  table in `dagger/src/buildout_ci/jobs.py`. Run a family with
  `dagger call ci --family <name>`, one cell with
  `dagger --progress=plain call job --name <cell>`, and poke a failed
  cell's container with `dagger call debug --name <cell> terminal`.
- In `--progress=plain` and CI logs, numbered cells map to their pins
  via the `withEnvVariable SETUPTOOLS_VERSION=...` /
  `withEnvVariable PIP_VERSION=...` lines — grep those to identify a
  failing leg.
- Always `--progress=plain` and tee to a log file for evidence.

## Engine anatomy

- Machine `devenv` (applehv), engine container `devenv-dagger`, image
  pulled by the devenv task `dagger:pull-engine`, engine config at
  `/etc/dagger/engine.toml` inside the VM (rewritten by the init
  script).
- **All engine state — including the build cache — lives in the
  podman volume `dagger-cache`** (mounted at `/var/lib/dagger`), not
  in the container. The container is disposable; the volume survives
  its removal. Both facts matter for the ladder below.
- Provisioning is the module's `dagger-engine-init` script (in the
  devenv shell PATH): it creates the volume and container when
  missing. Its `podman run` is *foreground by design* (built to run
  under `devenv up`) — when bringing the engine up by hand, use
  `nohup devenv shell -- dagger-engine-init &`.
- **Readiness probe:** `timeout 100 dagger core -s version` prints the
  engine version when ready. `dagger version` prints only the CLIENT
  line even when the engine is down — it is not a readiness check.

## Remediation ladder

Escalate in order; verify with the probe between rungs. (All four
rungs were needed on 2026-09-29 after the VM's filesystem corrupted
mid-run.)

1. **Machine down or SSH wedged** (podman socket `connection
   refused`; `podman machine ssh` exit 255 / handshake EOF):
   `podman machine stop devenv && podman machine start devenv`
   (a failed graceful stop falls back to a hard stop — fine).
2. **Engine container exited** (`podman --connection devenv ps -a`
   shows `devenv-dagger` Exited):
   `podman --connection devenv start devenv-dagger`.
3. **"container state improper" on exec** — runc state corrupt after
   a hard VM stop; `ps` can even show `Up` while exec fails:
   `podman rm -f devenv-dagger`, then
   `nohup devenv shell -- dagger-engine-init &`. The cache survives
   (it lives in the volume).
4. **Engine boots, then `fatal error: fault` / Go panic, or buildkit
   `input/output error` mid-run** — the cache volume itself is
   corrupted. Cold reset, which *loses the build cache*:
   `podman rm -f devenv-dagger`,
   `podman volume rm dagger-cache`,
   `nohup devenv shell -- dagger-engine-init &`.
   The next family run re-pulls all base images — budget ~2x the
   usual wall time.
5. Anything beyond rung 4 (recreating the machine itself) is an
   operator decision — the VM may hold other state.

## Run discipline

- **Freeze the checkout for the whole run.** Cells sync the working
  tree at call time, and a single-cell re-run re-syncs the CURRENT
  tree. Verify `git rev-parse HEAD` and a clean `git status --short`
  before launching; attribute results to that commit.
- **Never background a dagger call from an agent shell.** When the
  shell session ends, its children get SIGTERM and the engine
  connection dies mid-run; macOS has no `setsid`, and `nohup` does
  not help. Run foreground with a generous timeout, or hand the run
  to a subagent whose turn exists for that purpose.
- **Transient PyPI flakes are a known class** (SSL handshake/read
  timeouts, connection resets, both "No matching distribution"
  wordings during a cell's fetches): re-run the single failed cell
  once and report both outcomes. For persistent non-network failures,
  capture the verbatim tail (~40 lines) and re-run the cell once for
  determinism before diagnosing.
- **Post the verdict the moment it exists** — see the turn-budget
  rule in develop-buildout.
