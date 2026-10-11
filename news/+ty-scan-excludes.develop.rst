CI: exclude runtime-created artifact trees (``venvs``, ``eggs``,
``downloads``, ``bin``, ``develop-eggs``, ``parts``) from ty's project
scan: ty only respects ``.gitignore`` when ``.git`` is a directory,
which dagger and worktree-shaped checkouts do not guarantee, so the
static cell drowned in third-party diagnostics.  [gt-leader]
