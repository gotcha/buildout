from zc.buildout.buildout import print_


class Debug:

    def __init__(self, buildout, name, options):
        self.buildout = buildout
        self.name = name
        self.options = options

    def install(self):
        items = list(self.options.items())
        items.sort()
        for option, value in items:
            print_(f"  {option}={value!r}")
        return ()

    update = install
