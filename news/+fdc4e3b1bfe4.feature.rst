With ``installer = uv``, a non-default ``allow-hosts`` now warns that uv does not enforce it: uv has no host allow-list, and its ``--allow-insecure-host`` flag is TLS policy, not filtering. [gotcha]
