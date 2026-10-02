# Agent working agreement — zc.buildout

Before anything else, load the repo's skills:

- `.goose/skills/develop-buildout/` — the process side: every non-trivial
  change carries a towncrier news entry in `news/`; branches integrate by
  rebasing onto the base branch so merges stay fast-forward (no merge
  commits).
- `.goose/skills/verify-buildout/` — the behavioral side: drive
  `bin/buildout` from this checkout against throwaway projects the way a
  user would, plus the repo's two test suites (`make test` / `make
  pytest`) as the deep proof layer.

## Rules

- Plan first: no implementation before the plan has been reviewed and
  approved.
- Push policy: push only to your own fork remote. Never push to the
  remote that points at `github.com/buildout/buildout` without explicit
  approval — remote names vary per clone, check `git remote -v`.
- One task, one worktree: never work in a checkout another session or
  person is using — shared checkouts have produced wrong-branch commits.
- Suite doctrine: full `make test` unless the change is confined to CI
  yaml or agent guidance (`.github/workflows/`, `.goose/`), where no
  local suite can measure it; the verify ladder details live in the
  verify-buildout skill.
- Reporting: include CI run URLs, exact test counts, and commit hashes.
  If a verify rung was skipped, say which and why.
- Evidence must outlive the session: write it into the repo or the team
  workspace — never /tmp or disposable scratch dirs.
- If the CI matrix widens, re-verify on the new platform before claiming
  green.

## Closing the loop

- Every report ends in a terminal state: a result, a blocker, or a
  question. Work that shipped gets a closing line (merge hash, CI run
  URL) — no silent closes in either direction.
- The maintainer gives every delivered report a terminal signal: an
  acknowledgement (one line or an emoji) or a revision request. Wins get
  acknowledged too — agents calibrate on confirming signal, not only on
  correction.
- If a report hangs without a terminal signal, re-ping once. Never read
  silence as consent.
- A PR whose work landed is closed in the same act — never via GitHub's
  merge button: either marked merged by pushing the rebased head before
  the fast-forward, or closed with a comment naming the landing hashes
  and CI run. No PR hangs open after its work shipped; the command-level
  mechanics live in develop-buildout's linear-history section.
