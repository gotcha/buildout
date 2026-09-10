# Rerun and update modes

Buildout is designed for repeatable assembly: rerunning `buildout` on
an already-installed project is a fast no-op-ish update, `-N`
(non-newest) skips looking for newer distributions, and `-U` ignores
user-level defaults. These are the flags users rely on for CI and
deploys.

## Sub-features

- `rerun-clean` — a second `buildout` run on the same project succeeds
  without recreating the skeleton.
- `non-newest` — `-N` runs in non-newest mode (equivalent to
  `buildout:newest=false`).
- `no-user-defaults` — `-U` ignores `~/.buildout/default.cfg`.

## How to get to it (user POV)

- Run `bin/buildout` twice in the same project dir.
- Run `bin/buildout -N` to avoid seeking newer distributions.
- Run `bin/buildout -U` when user defaults must not leak in.

## Driving it with shell

Preconditions:

- Doctor all-OK; `PYTHONWARNINGS=ignore`; fresh `$D` with
  `printf '[buildout]\nparts =\n' > buildout.cfg`; `B` set.

- **First run.** `"$B" 2>&1 | tee "$ART/rerun-first.log"`. Exit 0;
  transcript has `Creating directory` lines.
- **Second run.** `"$B" 2>&1 | tee "$ART/rerun-second.log"`. Exit 0;
  transcript has NO `Creating directory` lines (skeleton exists).
  Diff the two transcripts into `$ART/rerun.diff` and assert the
  second is shorter.
- **Non-newest.** `"$B" -N 2>&1 | tee "$ART/rerun-N.log"`. Exit 0.
  Cross-check the equivalence claim:
  `"$B" -N query buildout:newest` prints `false`, while a plain
  `"$B" query buildout:newest` prints `true`.
- **User-defaults isolation.** `"$B" -U query buildout:directory`
  prints `$D`, exit 0. (On machines with a `~/.buildout/default.cfg`,
  compare `annotate` output with and without `-U`; on machines
  without, `-U` is a no-op — either way record which case applied in
  the transcript header.)

## Gotchas

- All of these are hermetic only with empty `parts =`; a real part
  re-pins versions and may hit the network on rerun without `-N`.
- `-N` still verifies installed distributions satisfy requirements —
  it is not an offline mode. Offline is the `buildout:offline=true`
  assignment.
- Second-run "no Creating directory" assertion applies to the empty
  baseline; after a real part install, expect `Updating <part>` lines
  instead.
