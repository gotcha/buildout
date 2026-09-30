Fix spurious mid-narrative part reinstalls under coverage runs:
``_dir_hash`` now ignores coverage's parallel-mode data files
(``.coverage.<host>.<pid>.<serial>``).  Under COVERAGE_PROCESS_START
every instrumented subprocess drops one into the checkout root — which
develop-dist recipe signatures hash — so a file landing between two
buildout runs flipped the signature and forced an
Uninstalling/Installing where the narrative expects an Updating (CI
flake: test_buildout_prefer_final_option on the coverage pytest job).
