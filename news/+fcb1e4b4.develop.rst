``make typecheck`` gates on Astral's ``ty`` with zero diagnostics over the
checkout: the test eggs are on ``ty``'s search path, the modules carry honest
annotations, and the remaining version- and platform-specific corners hold
scoped ``ty: ignore`` suppressions with the reason recorded inline.  [gotcha]
