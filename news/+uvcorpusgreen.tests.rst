More of the legacy doctest corpus runs under ``installer = uv``: recipe and
extension fixtures build wheels instead of eggs, the documentation examples
resolve their distributions through the repository's downloads directory, and
the egg-only doctests are skipped in uv mode (uv-deprecated).
[gotcha]
