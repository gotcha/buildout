#############################################################################
#
# Copyright (c) 2004-2009 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Various test-support utility functions
"""

import errno
import logging
import multiprocessing
import operator
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen

import pkg_resources

import zc.buildout.buildout
import zc.buildout.easy_install
from zc.buildout.rmtree import rmtree

print_ = zc.buildout.buildout.print_

fsync = getattr(os, 'fsync', lambda fileno: None)
is_win32 = sys.platform == 'win32'

def read(path='out', *rest):
    with open(os.path.join(path, *rest)) as f:
        return f.read()

def cat(dir, *names):
    path = os.path.join(dir, *names)
    if (not os.path.exists(path)
        and is_win32
        and os.path.exists(path+'-script.py')
        ):
        path = path+'-script.py'
    with open(path) as f:
        print_(f.read(), end='')

def eqs(a, *b):
    a = set(a)
    b = set(b)
    return None if a == b else (a - b, b - a)

def clear_here():
    for name in os.listdir('.'):
        if os.path.isfile(name) or os.path.islink(name):
            os.remove(name)
        else:
            shutil.rmtree(name)

def ls(dir, *subs, lowercase_and_sort_output=False):
    if subs:
        dir = os.path.join(dir, *subs)
    if lowercase_and_sort_output:
        # Get the original names, but sorted lowercase.
        names = sorted(os.listdir(dir), key=operator.methodcaller("lower"))
    else:
        names = sorted(os.listdir(dir))
    for name in names:
        # If we're running under coverage, elide coverage files
        if os.getenv("COVERAGE_PROCESS_START") and name.startswith('.coverage.'):
            continue
        if os.path.isdir(os.path.join(dir, name)):
            print_('d ', end=' ')
        elif os.path.islink(os.path.join(dir, name)):
            print_('l ', end=' ')
        else:
            print_('- ', end=' ')
        if lowercase_and_sort_output:
            name = name.lower()
        print_(name)

def mkdir(*path):
    os.mkdir(os.path.join(*path))

def remove(*path):
    path = os.path.join(*path)
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)

def rmdir(*path):
    shutil.rmtree(os.path.join(*path))

def write(dir, *args):
    path = os.path.join(dir, *(args[:-1]))
    with open(path, 'w') as f:
        f.write(args[-1])
        f.flush()
        fsync(f.fileno())

def clean_up_pyc(*path):
    base, filename = os.path.join(*path[:-1]), path[-1]
    if filename.endswith('.py'):
        filename += 'c' # .py -> .pyc
    for candidate in (
        os.path.join(base, filename),
        os.path.join(base, '__pycache__'),
        ):
        if os.path.isdir(candidate):
            rmdir(candidate)
        elif os.path.exists(candidate):
            remove(candidate)

## FIXME - check for other platforms
MUST_CLOSE_FDS = not sys.platform.startswith('win')

def system(command, input='', with_exit_code=False, env=None):
    # Some TERMinals, especially xterm and its variants, add invisible control
    # characters, which we do not want as they mess up doctests.  See:
    # https://github.com/buildout/buildout/pull/311
    # http://bugs.python.org/issue19884
    sub_env = dict(os.environ, TERM='dumb')
    if env is not None:
        sub_env.update(env)

    # We used to pass for example 'buildout annotate' as command, and call Popen
    # with 'shell=True'.  Since October 2024 this no longer works on Windows on GHA.
    # So we pass the command as a list.  But then it breaks on POSIX when we have
    # 'shell=True', because args[1:] gets passed as options for '/bin/sh' instead
    # of options for our command.  So let's let the value of 'shell' depend on
    # whether command is a list or a string.
    # See also https://stackoverflow.com/a/2401128/621201
    # Actually, having the command as a string turns out to only be a problem on
    # Windows if there is a space in the path, like with 'Program Files'.
    if isinstance(command, list):
        shell = False
    else:
        shell = True
    p = subprocess.Popen(command,
                         shell=shell,
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         close_fds=MUST_CLOSE_FDS,
                         env=sub_env)
    i, o, e = (p.stdin, p.stdout, p.stderr)
    # The PIPE arguments above guarantee these streams are not None.
    assert i is not None and o is not None and e is not None
    if input:
        i.write(input.encode())
    i.close()
    result = o.read() + e.read()
    o.close()
    e.close()
    output = result.decode()
    if with_exit_code:
        # Use the with_exit_code=True parameter when you want to test the exit
        # code of the command you're running.
        output += f'EXIT CODE: {p.wait()}'
    p.wait()
    return output

def get(url):
    return str(urlopen(url).read().decode())

def _runsetup(setup, *args):
    if os.path.isdir(setup):
        setup = os.path.join(setup, 'setup.py')
    args = list(args)
    args.insert(0, '-q')
    here = os.getcwd()
    try:
        os.chdir(os.path.dirname(setup))
        zc.buildout.easy_install.call_subprocess(
            [sys.executable, setup] + args,
            env=dict(os.environ,
                     PYTHONPATH=zc.buildout.easy_install.pip_pythonpath,
                     ),
            # Prevent showing several lines of output per created distribution,
            # especially with older setuptools versions.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            )
        if os.path.exists('build'):
            rmtree('build')
    finally:
        os.chdir(here)

def sdist(setup, dest):
    _runsetup(setup, 'sdist', '-d', dest)

def bdist_egg(setup, executable, dest=None):
    # Backward compat:
    if dest is None:
        dest = executable
    else:
        assert executable == sys.executable, (executable, sys.executable)
    _runsetup(setup, 'bdist_egg', '-d', dest)

def bdist_wheel(setup, dest):
    _runsetup(setup, 'bdist_wheel', '-d', dest)

def wait_until(label, func, *args, **kw):
    if 'timeout' in kw:
        kw = dict(kw)
        timeout = kw.pop('timeout')
    else:
        timeout = 30
    deadline = time.time()+timeout
    while time.time() < deadline:
        if func(*args, **kw):
            return
        time.sleep(0.01)
    raise ValueError('Timed out waiting for: '+label)

class TestOptions(zc.buildout.buildout.Options):

    def __init__(self, *args):
        zc.buildout.buildout.Options.__init__(self, *args)
        self._created = []

    def initialize(self):
        pass

class Buildout(zc.buildout.buildout.Buildout):

    def __init__(self):
        for name in os.path.join('eggs', 'v5'), 'parts':
            if not os.path.exists(name):
                os.makedirs(name)
        zc.buildout.buildout.Buildout.__init__(
            self, '', [('buildout', 'directory', os.getcwd())], False)

    Options = TestOptions

def hermetic_pip_env():
    """Cut test-spawned package installers off from any package index.

    The installers the suites spawn (pip or uv, for build isolation on
    sdist and editable installs, ``python -m build``) resolve their build
    requirements (setuptools, wheel) from the ambient index otherwise.
    With no index allowed and the wheels seeded by prepare.sh in
    downloads/test-seed as find-links, suite runs need no network index
    at all.

    uv specifics: uv reads no ``UV_NO_INDEX`` variable, and
    ``UV_OFFLINE`` cannot be used either: it blocks the localhost link
    server the corpus discovers packages through once uv does the
    resolving (``installer = uv``).  So hermeticity goes through a dead
    ``UV_INDEX_URL``: a ``file://`` path that does not exist fails
    instantly, never reaches the network, and find-links (the seed and
    the link server) stay usable.  Separately, uv's cache holds
    symlinked wheel entries that the doctest teardown
    (``zope.testing.setupstack.rmtree``) cannot remove, so the cache is
    redirected to a dedicated directory that ``restore`` deletes.

    Seam specifics: ``uv pip compile`` no longer honors the ambient
    ``UV_INDEX_URL``/``UV_FIND_LINKS`` — the seam scrubs them from the
    child environment so the configuration alone decides sources — so
    the seed and the dead index are injected as explicit seam arguments
    through ``buildout_testing_seam_find_links`` and
    ``buildout_testing_seam_index_url``.  The ambient variables stay
    set for the ``uv pip install`` step, whose build isolation still
    reads them.

    Returns a callable restoring the previous environment, or None when
    the seed directory is absent (tests run without prepare.sh): the
    ambient environment is then left alone, the pre-seed behavior.
    """
    seed = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        os.pardir, os.pardir, os.pardir, 'downloads', 'test-seed')
    if not os.path.isdir(seed):
        return None
    old = {name: os.environ.get(name)
           for name in ('PIP_NO_INDEX', 'PIP_FIND_LINKS',
                        'UV_INDEX_URL', 'UV_FIND_LINKS', 'UV_CACHE_DIR',
                        'buildout_testing_seam_find_links',
                        'buildout_testing_seam_index_url')}
    os.environ['PIP_NO_INDEX'] = '1'
    os.environ['PIP_FIND_LINKS'] = os.path.abspath(seed)
    os.environ['UV_INDEX_URL'] = 'file:///nonexistent-hermetic-index'
    os.environ['UV_FIND_LINKS'] = os.path.abspath(seed)
    os.environ['buildout_testing_seam_find_links'] = os.path.abspath(seed)
    os.environ['buildout_testing_seam_index_url'] = (
        'file:///nonexistent-hermetic-index')
    uv_cache = tempfile.mkdtemp('uv-cache')
    os.environ['UV_CACHE_DIR'] = uv_cache

    def restore():
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        rmtree(uv_cache)

    return restore


def buildoutSetUp(test):

    test.globs['__tear_downs'] = __tear_downs = []
    test.globs['register_teardown'] = register_teardown = __tear_downs.append

    prefer_final = zc.buildout.easy_install.prefer_final()
    register_teardown(
        lambda: zc.buildout.easy_install.prefer_final(prefer_final)
        )

    offline = zc.buildout.easy_install.offline()
    register_teardown(
        lambda: zc.buildout.easy_install.offline(offline)
        )

    here = os.getcwd()
    register_teardown(lambda: os.chdir(here))

    handlers_before_set_up = logging.getLogger().handlers[:]
    def restore_root_logger_handlers():
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        for handler in handlers_before_set_up:
            root_logger.addHandler(handler)
        bo_logger = logging.getLogger('zc.buildout')
        for handler in bo_logger.handlers[:]:
            bo_logger.removeHandler(handler)
    register_teardown(restore_root_logger_handlers)

    base = tempfile.mkdtemp('buildoutSetUp')
    base = os.path.realpath(base)
    register_teardown(lambda base=base: rmtree(base))

    old_home = os.environ.get('HOME')
    os.environ['HOME'] = os.path.join(base, 'bbbBadHome')
    def restore_home():
        if old_home is None:
            del os.environ['HOME']
        else:
            os.environ['HOME'] = old_home
    register_teardown(restore_home)

    base = os.path.join(base, '_TEST_')
    os.mkdir(base)

    tmp = tempfile.mkdtemp('buildouttests')
    register_teardown(lambda: rmtree(tmp))

    zc.buildout.easy_install.default_index_url = 'file://'+tmp
    os.environ['buildout_testing_index_url'] = (
        zc.buildout.easy_install.default_index_url)

    restore = hermetic_pip_env()
    if restore is not None:
        register_teardown(restore)

    def tmpdir(name):
        path = os.path.join(base, name)
        mkdir(path)
        return path

    sample = tmpdir('sample-buildout')

    os.chdir(sample)

    # Create a basic buildout.cfg to avoid a warning from buildout:
    with open('buildout.cfg', 'w') as f:
        f.write("[buildout]\nparts =\n")

    # Use the buildout bootstrap command to create a buildout
    zc.buildout.buildout.Buildout(
        'buildout.cfg',
        [('buildout', 'log-level', 'WARNING'),
         # trick bootstrap into putting the buildout develop egg
         # in the eggs dir.
         ('buildout', 'develop-eggs-directory', os.path.join('eggs', 'v5')),
         ]
        ).bootstrap([])



    # Create the develop-eggs dir, which didn't get created the usual
    # way due to the trick above:
    os.mkdir('develop-eggs')

    def start_server(path):
        port, thread = _start_server(path, name=path)
        url = f'http://localhost:{port}/'
        register_teardown(lambda: stop_server(url, thread))
        return url

    cdpaths = []
    def cd(*path):
        path = os.path.join(*path)
        cdpaths.append(os.path.abspath(os.getcwd()))
        os.chdir(path)

    def uncd():
        os.chdir(cdpaths.pop())

    test.globs.update({
        'sample_buildout': sample,
        'ls': ls,
        'cat': cat,
        'mkdir': mkdir,
        'rmdir': rmdir,
        'remove': remove,
        'tmpdir': tmpdir,
        'write': write,
        'system': system,
        'get': get,
        'cd': cd, 'uncd': uncd,
        'join': os.path.join,
        'sdist': sdist,
        'bdist_egg': bdist_egg,
        'start_server': start_server,
        'stop_server': stop_server,
        'buildout': os.path.join(sample, 'bin', 'buildout'),
        'wait_until': wait_until,
        'print_': print_,
        'clean_up_pyc': clean_up_pyc,
        'os': os,
        })

    zc.buildout.easy_install.prefer_final(prefer_final)

def buildoutTearDown(test):
    for f in test.globs['__tear_downs']:
        f()

class Server(HTTPServer):

    def __init__(self, tree, *args):
        HTTPServer.__init__(self, *args)
        self.tree = os.path.abspath(tree)

    __run = True
    def serve_forever(self, poll_interval: float = 0.5) -> None:
        # poll_interval is accepted for signature compatibility with
        # BaseServer.serve_forever; it is unused here.
        while self.__run:
            self.handle_request()

    def handle_error(self, request, client_address) -> None:
        self.__run = False

class Handler(BaseHTTPRequestHandler):

    # Dynamic class-attribute creation (name-mangled to _Server__log): moving
    # it into the Server class body breaks the HTTP test servers at runtime,
    # so it must stay here even though static analysis cannot see it.
    Server.__log = False  # ty: ignore[unresolved-attribute]

    def __init__(self, request, address, server):
        self.__server = server
        self.tree = server.tree
        BaseHTTPRequestHandler.__init__(self, request, address, server)

    def do_GET(self):
        if '__stop__' in self.path:
            self.__server.server_close()
            raise SystemExit

        def k():
            self.send_response(200)
            out = b'<html><body>k</body></html>\n'
            self.send_header('Content-Length', str(len(out)))
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(out)

        if self.path == '/enable_server_logging':
            self.__server.__log = True
            return k()

        if self.path == '/disable_server_logging':
            self.__server.__log = False
            return k()

        self._respond(head_only=False)

    def do_HEAD(self):
        # uv issues HEAD for artifact metadata before downloading.
        self._respond(head_only=True)

    def _respond(self, head_only):
        path = os.path.abspath(os.path.join(self.tree, *self.path.split('/')))
        if not (
            ((path == self.tree) or path.startswith(self.tree+os.path.sep))
            and
            os.path.exists(path)
            ):
            self.send_response(404, 'Not Found')
            #self.send_response(200)
            out = b'<html><body>Not Found</body></html>'
            #out = '\n'.join(self.tree, self.path, path)
            self.send_header('Content-Length', str(len(out)))
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            if not head_only:
                self.wfile.write(out)
            return

        self.send_response(200)
        if os.path.isdir(path):
            out = ['<html><body>\n']
            names = sorted(os.listdir(path))
            for name in names:
                if os.path.isdir(os.path.join(path, name)):
                    name += '/'
                out.append(f'<a href="{name}">{name}</a><br>\n')
            out.append('</body></html>\n')
            out = ''.join(out).encode()
            self.send_header('Content-Length', str(len(out)))
            self.send_header('Content-Type', 'text/html')
        else:
            if head_only:
                out = b''
                size = os.path.getsize(path)
            else:
                with open(path, 'rb') as f:
                    out = f.read()
                size = len(out)
            self.send_header('Content-Length', str(size))
            if path.endswith('.egg'):
                self.send_header('Content-Type', 'application/zip')
            elif path.endswith(('.gz', '.zip')):
                self.send_header('Content-Type', 'application/x-gzip')
            elif path.endswith('.whl'):
                self.send_header('Content-Type', 'application/octet-stream')
            else:
                self.send_header('Content-Type', 'text/html')

        self.end_headers()

        if not head_only:
            self.wfile.write(out)

    def log_request(self, code='-', size='-'):
        # size is accepted for signature compatibility with
        # BaseHTTPRequestHandler.log_request; it is unused here.
        if self.__server.__log:
            print_(f'{self.command} {code} {self.path}')

def _run(tree, port):
    server_address = ('localhost', port)
    httpd = Server(tree, server_address, Handler)
    httpd.serve_forever()
    httpd.server_close()

def get_port():
    for i in range(10):
        port = random.randrange(20000, 30000)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            try:
                s.connect(('localhost', port))
            except OSError:
                return port
        finally:
            s.close()
    raise RuntimeError("Can't find port")

def _start_server(tree, name=''):
    port = get_port()
    thread = threading.Thread(target=_run, args=(tree, port), name=name)
    thread.daemon = True
    thread.start()
    wait(port, up=True)
    return port, thread

def start_server(tree):
    return _start_server(tree)[0]

def stop_server(url, thread=None):
    try:
        urlopen(url+'__stop__')
    except Exception:  # noqa: BLE001, S110 - best-effort stop: the server may
        # already be gone
        pass
    if thread is not None:
        thread.join() # wait for thread to stop

def wait(port, up):
    addr = 'localhost', port
    for i in range(120):
        if i:
            # Don't sleep before the first try: the server is usually up
            # (or down) immediately, and 0.25s per server start adds up
            # fast in the test suite.
            time.sleep(0.25)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(addr)
            s.close()
            if up:
                break
        except OSError as e:
            if e.errno not in (errno.ECONNREFUSED, errno.ECONNRESET):
                raise
            s.close()
            if not up:
                break
    else:
        if up:
            raise  # noqa: PLE0704 - pre-existing retry-exhaustion rethrow;
            # no active exception here, so this surfaces RuntimeError today.
            # Changing the raised type is behavior work, out of burndown scope.
        else:
            raise SystemError("Couldn't stop server")

def install(project, destination):
    if not isinstance(destination, str):
        destination = os.path.join(destination.globs['sample_buildout'],
                                   'eggs')

    dist = pkg_resources.working_set.find(
        pkg_resources.Requirement.parse(project))
    if dist is None:
        raise ValueError(f'Distribution not found for {project!r}')
    if dist.location is None:
        raise ValueError(f'Distribution {project!r} has no location')
    if dist.location.endswith('.egg'):
        destination = os.path.join(destination,
                                   os.path.basename(dist.location),
                                   )
        if os.path.isdir(dist.location):
            shutil.copytree(dist.location, destination)
        else:
            shutil.copyfile(dist.location, destination)
    else:
        # copy link
        with open(os.path.join(destination, project+'.egg-link'), 'w') as f:
            f.write(dist.location)

def install_develop(project, destination):
    if not isinstance(destination, str):
        destination = os.path.join(destination.globs['sample_buildout'],
                                   'develop-eggs')

    dist = pkg_resources.working_set.find(
        pkg_resources.Requirement.parse(project))
    if dist is None:
        raise ValueError(f'Distribution not found for {project!r}')
    if dist.location is None:
        raise ValueError(f'Distribution {project!r} has no location')
    with open(os.path.join(destination, project+'.egg-link'), 'w') as f:
        f.write(dist.location)

def _normalize_path(match):
    path = match.group(1)
    if os.path.sep == '\\':
        path = path.replace('\\\\', '/')
        path = path.removeprefix('\\')
    return '/' + path.replace(os.path.sep, '/')

normalize_path = (
    re.compile(
        rf'''[^'" \t\n\r]+\{os.path.sep}_[Tt][Ee][Ss][Tt]_\{os.path.sep}([^"' \t\n\r]+)'''),
    _normalize_path,
    )

normalize_endings = re.compile('\r\n'), '\n'

# zc.buildout declares ``tomli; python_version < "3.11"`` (uv_resolve's TOML
# reader falls back to it where the stdlib lacks tomllib). On 3.9 and 3.10
# the toolchain closure in easy_install.buildout_and_setuptools_dists gains a
# tomli dist, and the sample bootstrap writes a tomli.egg-link into the eggs
# directory. Listings that pin the toolchain egg-links cannot hold on both
# sides of the 3.11 boundary, so drop the conditional line; the rest of the
# listing stays strictly checked. Inert where tomli is not installed.
# A (pattern, replacement) pair rather than a function so the pytest
# harness (tests/pytests/conftest.py apply_normalizers) applies it too.
drop_tomli_egg_link = (
    re.compile(r'(?m)^-  tomli\.egg-link\n'), '',
    )

def drop_build_output_relayed_by_pip(text):
    """Drop lines that only appear because pip relays build subprocess output.

    pip relays the stdout of the sdist builds it spawns; uv does not.
    Expectations pinning such lines (the extdemo setup.py printing the
    environment it sees) cannot hold under ``installer = uv``. Dropping
    them there keeps the rest of the transcript strictly checked; the
    environment propagation itself is still proven by the egg building
    successfully. Inert under pip.
    """
    if zc.buildout.easy_install.installer() != 'uv':
        return text
    return re.sub(
        r'.*Have environment test_environment_variable:.*\n', '', text)

def drop_uv_link_server_requests(text):
    """Drop link-server request lines from transcripts in uv mode.

    uv interrogates a link server differently than the vendored scraper:
    it lists directory pages, probes the index for every project, issues
    HEAD requests for artifact metadata, revalidates archives through
    its cache, and serves repeats from that cache without any request at
    all. No request sequence written for the scraper can hold under uv,
    and uv's real fetching is asserted end to end by
    tests/pytests/test_uv_integration.py. So in uv mode the request
    lines are dropped on both sides of the comparison; the remaining
    log lines (Getting distribution, Got, Develop) stay strictly
    checked. Inert under pip.
    """
    if zc.buildout.easy_install.installer() != 'uv':
        return text
    return re.sub(r'(?m)^(?:GET|HEAD) \S.*\n', '', text)

def drop_uv_version_chatter(text):
    """Drop the ``Using uv ...`` debug lines in uv mode.

    The seam logs the uv binary and version at debug level, once per
    resolve and once per install; log-transcript expectations written
    for pip have no place for those lines. Inert under pip.
    """
    if zc.buildout.easy_install.installer() != 'uv':
        return text
    return re.sub(r'[^\n]* DEBUG\n *Using uv [^\n]*\n', '', text)

_UV_CACHE_SERVED_LINES = frozenset([
    'GET 200 /demo-0.2-py3-none-any.whl',
    'GET 200 /demoneeded-1.1.tar.gz',
    'GET 200 /extdemo-1.5.tar.gz',
    '-  demo-0.2-py3-none-any.whl',
    '-  demoneeded-1.1.tar.gz',
])

def normalize_uv_download_cache(text):
    """Drop lines pinning download-cache population in uv mode.

    With installer = uv, wheels and sdists are fetched and kept by uv
    itself: the download cache is not populated, and later installs
    revalidate through uv's cache instead of being served from the
    download cache. Expectations written for pip pin the demo wheel and
    the demoneeded and extdemo sdists landing in, and being served
    from, the download cache; uv mode never produces those lines.
    Dropping them on both sides keeps the rest of the transcript
    strictly checked. Inert under pip.

    Tagged uv-deprecated: remove together with the download-cache
    support.
    """
    if zc.buildout.easy_install.installer() != 'uv':
        return text
    return '\n'.join(
        line for line in text.split('\n')
        if line not in _UV_CACHE_SERVED_LINES)

def drop_uv_resolution_stderr_tail(text):
    """Drop the uv stderr tail lines of a MissingDistribution in uv mode.

    With installer = uv, a distribution uv cannot find reports the tail
    of uv's stderr after the Couldn't-find-a-distribution line, so the
    cause class stays visible; uv's wording is uv's own and changes
    between releases, so transcripts written for pip drop those lines.
    Inert under pip.
    """
    if zc.buildout.easy_install.installer() != 'uv':
        return text
    return re.sub(r'(?m)^  uv: [^\n]*\n', '', text)

def drop_uv_allow_hosts_warning(text):
    """Drop the allow-hosts warning lines in uv mode.

    Spawned buildouts warn once per run when allow-hosts differs from
    the default under ``installer = uv``, so every transcript of such a
    run would have to pin it.  The warning itself is asserted by unit
    and corpus tests.  Inert under pip.
    """
    if zc.buildout.easy_install.installer() != 'uv':
        return text
    return re.sub(r'(?m)^.*allow-hosts option is not enforced.*\n', '', text)


def drop_uv_download_cache_deprecation(text):
    """Drop the download-cache deprecation warning lines in uv mode.

    Spawned buildouts log the deprecation once per process, so every
    transcript of a download-cache run would have to pin it. The warning
    is asserted by a unit test instead. Inert under pip.

    Tagged uv-deprecated: remove together with the download-cache
    support.
    """
    if zc.buildout.easy_install.installer() != 'uv':
        return text
    return re.sub(r'.*the download-cache is not populated.*\n', '', text)

normalize_script = (
    re.compile('(\n?)-  ([a-zA-Z_.-]+)-script.py\n-  \\2.exe\n'),
    '\\1-  \\2\n')

normalize___pycache__ = (
    re.compile('(\n?)d  __pycache__\n'), '\\1')

normalize_egg_py = (
    re.compile(r'-py\d[.]\d+(-\S+)?\.egg'),
    '-pyN.N.egg',
    )

normalize_exception_type_for_python_2_and_3 = (
    re.compile(r'^(\w+\.)*([A-Z][A-Za-z0-9]+Error: )'),
    '\2')

normalize_open_in_generated_script = (
    re.compile(r"open\(__file__, 'U'\)"), 'open(__file__)')

not_found = (re.compile(r'Not found: [^\n]+/(\w|\.|-)+/\r?\n'), '')

easyinstall_deprecated = (re.compile(r'.*EasyInstallDeprecationWarning.*\n'),'')
setuptools_deprecated = (re.compile(r'.*SetuptoolsDeprecationWarning.*\n'),'')
pkg_resources_deprecated = (re.compile(r'.*PkgResourcesDeprecationWarning.*\n'),'')
warnings_warn = (re.compile(r'.*warnings\.warn.*\n'),'')

# Setuptools now pulls in dependencies when installed.
adding_find_link = (re.compile(r"Adding find link '[^']+'"
                               r" from setuptools .*\r?\n"), '')

ignore_not_upgrading = (
    re.compile(
    'Not upgrading because not running a local buildout command.\n'
    ), '')

# The root logger from setuptools prints all kinds of lines.
# This might depend on which setuptools version, or something else,
# because it did not happen before.  Sample lines:
# "root: Couldn't retrieve index page for 'zc.recipe.egg'"
# "root: Scanning index of all packages.
# "root: Found: /sample-buildout/recipe/dist/spam-2-pyN.N.egg"
# I keep finding new lines like that, so let's ignore all.
ignore_root_logger = (re.compile(r'root:.*'), '')
# Now replace a multiline warning about that you should switch to native namespaces.
ignore_native_namespace_warning_1 = (re.compile(r'!!'), '')
ignore_native_namespace_warning_2 = (re.compile(r'\*' * 80), '')
ignore_native_namespace_warning_3 = (re.compile(
    r'Please replace its usage with implicit namespaces \(PEP 420\).'),
    ''
)
ignore_native_namespace_warning_4 = (re.compile(
    r'See https://setuptools.pypa.io/en/latest/references/keywords.html#keyword-namespace-packages for details.'),
    ''
)
ignore_native_namespace_warning_5 = (re.compile(
    r'ep.load\(\)\(self, ep.name, value\)'),
    ''
)


def run_buildout(command):
    # Make sure we don't get .buildout
    os.environ['HOME'] = os.path.join(os.getcwd(), 'home')
    args = command.split()
    buildout = pkg_resources.load_entry_point(
        'zc.buildout', 'console_scripts', args[0])
    buildout(args[1:])

def run_from_process(target, *args, **kw):
    with open('out', 'w') as out:
        sys.stdout = sys.stderr = out
        target(*args, **kw)

def run_in_process(*args, **kwargs):
    try:
        ctx = multiprocessing.get_context('fork')
        process = ctx.Process(target=run_from_process, args=args, kwargs=kwargs)
    except AttributeError:
        process = multiprocessing.Process(target=run_from_process, args=args, kwargs=kwargs)
    process.daemon = True
    process.start()
    process.join(99)
    if process.is_alive() or process.exitcode:
        with open('out') as f:
            print(f.read())

def run_buildout_in_process(command='buildout'):
    options = (
        " use-dependency-links=false"
        # Leaving this here so we can uncomment to see what's going on.
        #" log-format=%(asctime)s____%(levelname)s_%(message)s -vvv"
        " index=" + __file__ + 'nonexistent' # hide index
        )
    if zc.buildout.easy_install.installer() == 'uv':
        # In pip mode the vendored package index also scans the test
        # runner's sys.path, so the documentation examples resolve the
        # distributions they install from the repository's eggs
        # directory. uv only consults explicit find-links and indexes,
        # so point it at the distributions the repository's own
        # buildout run downloads. Inert under pip.
        repo = os.path.dirname(os.path.abspath(__file__))
        for _ in range(3):
            repo = os.path.dirname(repo)
        distros = os.path.join(repo, 'downloads', 'dist')
        if os.path.isdir(distros):
            options += ' find-links=' + distros
    # The annotation keeps the list element type as plain str: without it
    # the inferred element type is LiteralString (from the literal default),
    # which rejects inserting the non-literal `options` string.
    parts: list = command.split(' ', 1)
    parts.insert(1, options)
    run_in_process(run_buildout, ' '.join(parts))
