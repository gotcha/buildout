``test_workingset_adapters`` portability: fixture eggs are tagged with
the running interpreter (was: hard-coded ``py3.12``, which silently
emptied the fixtures on every other Python) and the platform-egg
expectation in the environment-scan guard is macOS-aware.  The module
had been failing six tests on the Linux CI legs since its introduction;
it now passes there.  [Fizz]
