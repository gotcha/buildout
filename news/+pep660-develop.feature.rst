``develop =`` now works for pyproject-only (PEP 660) packages such as
hatchling-backed sources, in both pip and uv installer modes (Phase 5 of
the uv dependency removal plan).  Such an editable install writes no
metadata into the source checkout, so the dist used to stay invisible
and the run failed with "Couldn't find a distribution".  The editable
install's ``.dist-info`` and ``.pth`` are now kept in the develop-eggs
directory (a port of upstream buildout/buildout#746's approach), where
the working-set scanner, generated scripts, and the buildout process
itself can all see the package.  Editable installs carried only by an
import-hook ``.pth`` line, with no metadata in the checkout either, are
outside the supported layouts: their metadata is kept, but imports from
generated scripts will fail.  [gt-coleader]
