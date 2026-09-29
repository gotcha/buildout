Fix uv-mode egg moves under setuptools older than 71:
``_get_matching_dist_in_location`` compared ``parsed_version`` tuples
across packaging classes — the facade's distributions parse with the
real ``packaging``, while a ``pkg_resources.parse_version`` result on
older setuptools comes from its vendored copy, and two different
``Version`` classes never compare equal, so an egg whose version
normalizes (3.3.0 sought, 3.3 on disk, see PR #452) failed to match and
moving it raised ``has no distribution``.  Both sides are now re-parsed
with the same parser before comparing; legacy versions that packaging
cannot parse keep their exact-string semantics.  [Fizz]
