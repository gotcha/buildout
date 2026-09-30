Fix uv-mode semantics on setuptools < 68 legs, where the installed
pkg_resources (kept by design over the vendored copy) backs the
runtime:

- The patched ``Requirement.__contains__`` was isinstance-gated on the
  live copy's ``Distribution``, so uv mode's facade dists
  (``_workingset.Distribution``) fell through to
  ``SpecifierSet.contains(object)`` — which old vendored packagings
  raise ``TypeError`` on, reported as "not contained".  The patch now
  accepts any dist-shaped object (key + version).
- ``_pin_beats_env_dist`` compared ``env_dist.parsed_version`` (the old
  copy's vendored-packaging ``Version``) against this packaging's
  ``Version`` — a cross-class ``TypeError``.  The env version is now
  re-parsed from the string with this packaging, falling back to the
  forgiving ``parsed_version`` for unparseable versions.
