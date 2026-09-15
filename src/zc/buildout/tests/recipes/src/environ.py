import os
import sys


class Environ:

    def __init__(self, buildout, name, options):
        self.buildout = buildout
        self.options = options

    def install(self):
        _ = self.options['name']
        sys.stdout.write(f"HOME {os.environ['HOME']}\\n")
        sys.stdout.write(f"USERPROFILE {os.environ['USERPROFILE']}\\n")
        sys.stdout.write(f"expanduser {os.path.expanduser('~')}\\n")
        return ()

    update = install
