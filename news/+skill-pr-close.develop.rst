``develop-buildout`` gains the PR closure mechanics: integration is
local rebase + fast-forward only (GitHub's merge button is never used),
a topic branch backing an open PR may be force-pushed with
``--force-with-lease`` so the PR head tracks the rebased tip, and a
landed PR is either marked merged by GitHub's base-equals-head detection
or closed with a comment naming the landing hashes and CI run.  [Pollen]
