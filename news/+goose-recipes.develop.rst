Add two project recipes under ``.goose/recipes/``: ``worktree-task``
runs one task in its own worktree, verified per the repo skills and
reported in the standard shape without pushing; ``push-and-watch-ci``
pushes only to an allowlisted fork remote, reports the CI run URL as
soon as the run exists, and reports the conclusion.  [Pollen]
