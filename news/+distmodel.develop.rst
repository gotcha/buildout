uv dependency removal, Phase 2 unit 6b: grow the uv-mode distribution
model in ``zc.buildout._workingset`` — ``Requirement``/``Distribution``
adapters, an ``Environment`` port with byte-pinned pkg_resources parity
(name normalization, hashcmp ordering, ``insert_on``, dep-map requires,
scan precedence, macOS platform acceptance), and ``VersionConflict`` /
``UnknownExtra`` shapes. Additive only: nothing consumes the adapters
yet; pinned by a new parity test table against live pkg_resources.
[Fizz]
