import os
import stat
import tempfile

import pytest

from zc.buildout.rmtree import rmtree


def test_rmtree_removes_directory():
    d = tempfile.mkdtemp()
    assert os.path.isdir(d)
    rmtree(d)
    assert not os.path.isdir(d)


def test_rmtree_removes_readonly_file():
    d = tempfile.mkdtemp()
    foo = os.path.join(d, "foo")
    with open(foo, "w") as f:
        f.write("huhu")
    os.chmod(foo, 0o400)
    rmtree(d)
    assert not os.path.isdir(d)
