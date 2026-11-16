"""pybars' own test suite, for the installed pybars.

It is ``tests/`` at the root of the repository when pybars is the one of the
repository, or the directory that ``PYBARS_TESTS`` names, such as the
``tests/`` of the ``0.9.6`` tag.
"""

import importlib
import importlib.util
import os
import sys

import pybars._compiler

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def same_file(first, second):
    try:
        with open(first, 'rb') as left, open(second, 'rb') as right:
            return left.read() == right.read()
    except OSError:
        return False


def find():
    """
    Finds pybars' test suite for the installed pybars

    :return:
        A tuple of (directory, None), or (None, why it was not found)
    """

    directory = os.environ.get('PYBARS_TESTS')
    if directory:
        return directory, None
    if same_file(pybars._compiler.__file__, os.path.join(ROOT, 'pybars', '_compiler.py')):
        return os.path.join(ROOT, 'tests'), None
    return None, 'the installed pybars is not the one of this repository: set PYBARS_TESTS to its test suite'


def load(directory):
    """
    Imports pybars' test suite as the ``pybars_tests`` package: pybars3-rs'
    tests are a ``tests`` package too, and pybars' modules import each other

    :param directory:
        The directory of pybars' tests

    :return:
        A tuple of the test_acceptance and test__compiler modules
    """

    spec = importlib.util.spec_from_file_location(
        'pybars_tests', os.path.join(directory, '__init__.py'), submodule_search_locations=[directory])
    package = importlib.util.module_from_spec(spec)
    sys.modules['pybars_tests'] = package
    spec.loader.exec_module(package)
    return importlib.import_module('pybars_tests.test_acceptance'), importlib.import_module('pybars_tests.test__compiler')
