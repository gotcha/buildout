New ``dagger call ci`` job in the test workflow: the whole matrix runs a
second time inside containers via the repo's dagger module, with the
runner's docker daemon self-provisioning the engine. The dagger CLI comes
from ``dagger/dagger-for-github`` pinned to ``dagger.json``'s engine
version — a second documented exception to the devenv-only provisioning
rule, after the Windows job. [gotcha]
