"""The comparison harness itself: it must notice when pybars_rs and pybars differ."""

import contextlib
import io
import os
import tempfile
import types
import unittest

import pybars
import pybars_rs

from tests import corpus, mutants, parity

#: The fewest mutants that apply to a pybars release.
MIN_MUTANTS = 8


class TestHarness(unittest.TestCase):

    def test_every_pybars_mutant_is_caught_by_its_seed(self):
        applicable = mutants.applicable_mutants()
        self.assertGreaterEqual(len(applicable), MIN_MUTANTS)
        for from_text, to_text, seed, description in applicable:
            with self.subTest(description):
                self.assertIn(seed, corpus.SEED_CORPUS)
                self.assertFalse(parity.check_all([seed]).mismatches)
                with mutants.mutated_pybars(from_text, to_text):
                    report = parity.check_all([seed])
                self.assertTrue(report.mismatches, 'the harness did not notice: ' + description)

    def test_a_mutant_needs_its_target_text(self):
        with self.assertRaises(LookupError), mutants.mutated_pybars("not in pybars' source", ''):
            pass

    def test_the_mutants_leave_pybars_as_it_was(self):
        original = pybars.Compiler
        with mutants.mutated_pybars(*mutants.applicable_mutants()[0][:2]):
            self.assertIsNot(pybars.Compiler, original)
        self.assertIs(pybars.Compiler, original)

    def test_the_checked_compiler_is_removed_afterwards(self):
        # A module that, like pybars' tests, ran `from pybars import Compiler`.
        upstream = types.ModuleType('upstream')
        upstream.Compiler = pybars.Compiler
        exec('def render(source, context):\n    return Compiler().compile(source)(context)\n', upstream.__dict__)

        with parity.checked_compiler(upstream) as counts:
            self.assertTrue(issubclass(pybars.Compiler, pybars_rs.Compiler))
            self.assertIs(upstream.Compiler, pybars.Compiler)
            upstream.render('{{a}}', {'a': 1})
        self.assertEqual(counts['calls'], 1)
        self.assertEqual(counts['fast_path'], 1)
        self.assertIs(upstream.Compiler, pybars.Compiler)
        self.assertFalse(issubclass(pybars.Compiler, pybars_rs.Compiler))

    def test_differences_are_described(self):
        same = parity.Outcome('abc')
        self.assertIsNone(parity.difference(same, parity.Outcome('abc')))
        self.assertIn('differs at 1', parity.difference(same, parity.Outcome('aXc')))
        raised = parity.Outcome(None, ValueError, 'boom')
        self.assertEqual(parity.difference(same, raised), 'pybars source(3 chars), pybars_rs ValueError: boom')
        self.assertEqual(parity.first_difference('ab', 'abc'), 2)
        self.assertEqual(parity.safe_repr('\ud800'), "'\\ud800'")

    def test_the_corpus_mode_prints_only_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, 'secret.hbs'), 'w') as template:
                template.write('{{#if customer_secret}}value{{/if}}')
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(parity.check_directory(directory), 0)
            self.assertIn('1 templates: fast path 1', printed.getvalue())
            self.assertNotIn('customer_secret', printed.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                # An empty corpus is not a pass.
                self.assertEqual(parity.check_directory(os.path.join(directory, 'empty')), 1)

    def test_the_command_line_fuzzes(self):
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(parity.main(['--fuzz', '200', '--seed', '7']), 0)
        self.assertIn('no mismatches', printed.getvalue())
