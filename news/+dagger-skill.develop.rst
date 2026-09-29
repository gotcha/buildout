Agent skills: new ``dagger`` skill documents the local CI engine's
anatomy (state lives in the ``dagger-cache`` volume, not the container),
the ``dagger core -s version`` readiness probe, a four-rung remediation
ladder for a wedged engine (machine, container, cache volume), and the
frozen-tree / foreground / flake-rerun run discipline;
``develop-buildout`` cross-references it from its local-dagger section.
[Fizz]
