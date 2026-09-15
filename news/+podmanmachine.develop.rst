Code the podman machine resources in ``devenv.nix``
(``services.podman-machine.memoryMiB = 8192``, ``cpus = 6``) instead of
relying on hand-set machine state: the podman default of 2048 MiB
OOM-killed the CI cache workload under a full run, and a fresh machine
would have silently gotten it again. Requires the ``memoryMiB``/``cpus``
options added upstream in jfroche/devenv-dagger#2; the lock now pins
that rev.
