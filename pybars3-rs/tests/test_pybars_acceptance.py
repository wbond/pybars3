"""pybars' own test suite, with ``pybars_rs.Compiler`` as ``pybars.Compiler``.

Every compile is also run through pybars itself, and a different result fails
the test (``parity.checked_compiler``). The suite is the one of the installed
pybars: ``tests/`` at the root of the repository when pybars is the one of the
repository, or the directory that ``PYBARS_TESTS`` names, such as the
``tests/`` of the ``0.9.6`` tag.
"""

import collections
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import pybars
import pybars._compiler
import pybars_rs

from tests import parity, upstream

#: The fewest tests pybars' suite has (pybars3 0.9.6 has 166).
MIN_UPSTREAM_TESTS = 166

UPSTREAM_DIRECTORY, SKIP_REASON = upstream.find()
if UPSTREAM_DIRECTORY is not None:
    _ACCEPTANCE, _COMPILER = upstream.load(UPSTREAM_DIRECTORY)

#: What the checked compiler saw while the upstream tests ran.
COUNTS = collections.Counter()


class _CheckedCompiler:

    """Runs a pybars test case with the checked compiler as ``Compiler``."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The upstream modules ran `from pybars import Compiler` when imported.
        cls._checked = parity.checked_compiler(_ACCEPTANCE, _COMPILER)
        cls._counts = cls._checked.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._checked.__exit__(None, None, None)
        counts = cls._counts
        COUNTS.update(counts)
        super().tearDownClass()
        # Every template took the fast path (pybars' suite compiles a few
        # non-strings, which it expects to fail): the suite tests the port,
        # not the fallback.
        if not set(counts) - {'monkeypatched'} <= {'calls', 'fast_path', 'not_str'}:
            raise AssertionError(counts)
        if counts['fast_path'] != counts['calls'] - counts['not_str'] - counts['monkeypatched']:
            raise AssertionError(counts)

    def setUp(self):
        super().setUp()
        # test_precompile writes a module to the working directory and imports it.
        directory = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(directory)
        sys.path.insert(0, directory)
        self.addCleanup(shutil.rmtree, directory)
        self.addCleanup(sys.path.remove, directory)
        self.addCleanup(os.chdir, cwd)


if UPSTREAM_DIRECTORY is None:

    @unittest.skip(SKIP_REASON)
    class TestUpstreamAcceptance(unittest.TestCase):
        def test_skipped(self):
            pass

    @unittest.skip(SKIP_REASON)
    class TestUpstreamCompiler(unittest.TestCase):
        def test_skipped(self):
            pass

else:

    class TestUpstreamAcceptance(_CheckedCompiler, _ACCEPTANCE.TestAcceptance):
        pass

    class TestUpstreamCompiler(_CheckedCompiler, _COMPILER.TestCompiler):
        pass


@unittest.skipIf(UPSTREAM_DIRECTORY is None, SKIP_REASON)
class TestUpstreamSuite(unittest.TestCase):

    def test_the_whole_upstream_suite_is_collected(self):
        tests = unittest.defaultTestLoader.getTestCaseNames
        count = len(tests(TestUpstreamAcceptance)) + len(tests(TestUpstreamCompiler))
        self.assertGreaterEqual(count, MIN_UPSTREAM_TESTS)
        self.assertEqual(count, len(tests(_ACCEPTANCE.TestAcceptance)) + len(tests(_COMPILER.TestCompiler)))

    def test_upstream_compiles_go_through_pybars_rs(self):
        with parity.checked_compiler(_ACCEPTANCE, _COMPILER):
            self.assertIs(_ACCEPTANCE.Compiler, pybars.Compiler)
            self.assertIs(_COMPILER.Compiler, pybars.Compiler)
            self.assertTrue(issubclass(pybars.Compiler, pybars_rs.Compiler))
            template = _ACCEPTANCE.Compiler().compile('Hello {{name}}!')
            self.assertEqual(str(template({'name': 'world'})), 'Hello world!')

    def test_a_disagreement_fails_even_inside_a_broad_except(self):
        def wrong(_compiler, _source):
            return pybars._compiler.FunctionContainer('render', '# not what pybars generates\n')

        def compile_inside_a_broad_except():
            try:
                _ACCEPTANCE.Compiler().compile('{{a}}')
            except Exception:  # the point of the test
                self.fail('OracleMismatch was caught by `except Exception`')

        with mock.patch.object(parity, 'fast_path', lambda _source: (None, 'monkeypatched')), \
                mock.patch.object(pybars_rs.Compiler, '_generate_code', wrong), \
                parity.checked_compiler(_ACCEPTANCE, _COMPILER):
            with self.assertRaises(parity.OracleMismatch):
                compile_inside_a_broad_except()
