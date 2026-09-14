Dagger CI: ``dagger call ci --family <name>`` runs a single job family
(``setuptools``, ``python``, ``pip``, ``scripts``, ``static``,
``coverage``; listed by ``dagger call families``), and
``dagger call jobs`` gained the same filter. The GitHub ``dagger`` job is
now a matrix over the six families, so runners parallelize again.
[gotcha]
