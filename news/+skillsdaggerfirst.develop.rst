Agent skills updated: verify-buildout now leads with the daggerized CI
axis (``dagger call smoke``/``job``/``ci``) for any answer that must
match CI, with measured cache expectations and a smoke-ordering rule
(smoke before the suites for bootstrap-path changes, after them on the
push candidate), and documents the suites' index-hermetic pip seeding;
develop-buildout records the no-proxy cell design and the retry's role
as PyPI-outage tolerance. [gotcha]
