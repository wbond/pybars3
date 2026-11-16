"""Properties that hold for every template, checked with Hypothesis.

``HYPOTHESIS_PROFILE=long`` runs many more examples than CI does.
"""

import unittest

from hypothesis import example, given
from hypothesis import strategies as st
import pybars
import pybars_rs

from tests import parity, strategies


class Text(str):

    """A ``str`` subclass, which pybars 0.9.6 parses through its own methods."""

    __slots__ = ()


class TestProperties(unittest.TestCase):

    def assertMatchesPybars(self, source):
        report = parity.check_all([source])
        self.assertFalse(report.mismatches, report.failure_message())

    @given(strategies.templates)
    @example('{{#if a}}x{{else}y{{/if}}')
    @example('{{> part aa=(missing) [aa]=2}}')
    @example('x\n {{~#if a~}} \n{{else}}\r\n{{/if}}\n')
    def test_grammar_shaped_templates_match_pybars(self, source):
        self.assertMatchesPybars(source)

    @given(st.text(max_size=40))
    def test_any_text_matches_pybars(self, source):
        self.assertMatchesPybars(source)

    @given(st.text(st.sampled_from(list('{}#^/!>&.[]() =~"\'ab1\t\r\n')), max_size=24))
    def test_template_syntax_soup_matches_pybars(self, source):
        self.assertMatchesPybars(source)

    @given(strategies.well_formed)
    def test_str_subclasses_run_pybars(self, source):
        before = pybars_rs.counters()['not_str']
        expected = parity.Outcome.capture(lambda: pybars.Compiler().precompile(Text(source)))
        actual = parity.Outcome.capture(lambda: pybars_rs.Compiler().precompile(Text(source)))
        self.assertEqual(expected, actual)
        self.assertEqual(pybars_rs.counters()['not_str'], before + 1)

    @given(strategies.well_formed)
    def test_compiled_templates_render_like_pybars(self, source):
        context = {'a': 1, 'b': [1, 2]}
        expected = parity.Outcome.capture(lambda: str(pybars.Compiler().compile(source)(context)))
        actual = parity.Outcome.capture(lambda: str(pybars_rs.Compiler().compile(source)(context)))
        self.assertEqual(expected, actual)
