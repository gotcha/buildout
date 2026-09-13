# Complexity gate: `make complexity`

The complexity budget gate keeps cyclomatic complexity from growing
back while the reduction work proceeds. It is a static tier: it reads
only the source tree, runs in seconds, and never substitutes for the
suites.

## What runs

`make complexity` executes `etc/complexity_gate.py` (stdlib-only),
which scans `src/zc/buildout` with radon (from the devenv) and
compares every function and method against the checked-in baseline
`etc/complexity-baseline.json`:

- a block more complex than its baseline entry fails the gate;
- a block with no baseline entry must be radon grade B or better
  (CC <= 10);
- blocks that got simpler or disappeared are printed as progress.

## When it fails

The gate fails on exactly two events: existing code got worse, or new
code arrived above the budget. Both are commit-time signals to extract
or simplify, not to negotiate with the baseline.

## Refreshing the baseline

Only after a simplification lands and the suites agree:

```sh
make complexity-baseline
git add etc/complexity-baseline.json
```

Never refresh to make a regression pass — the diff of the baseline is
part of the review.

## Evidence

Record the gate's last line like a suite total: `complexity gate OK:
N blocks within budget`, plus `git rev-parse HEAD`. A baseline refresh
adds the `improved:` / `gone:` lines to the transcript.
