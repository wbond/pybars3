"""The templates that pin down pybars' behaviour, each compared with pybars."""

import unittest

import pybars
import pybars_rs

from tests import corpus, parity

IS_0_9_7 = pybars.__version__ == '0.9.7'


class TestSeedCorpus(unittest.TestCase):

    def test_seed_templates_match_pybars(self):
        for source in corpus.SEED_CORPUS:
            with self.subTest(source=parity.safe_repr(source)):
                report = parity.check_all([source])
                self.assertFalse(report.mismatches, report.failure_message())

    def test_surprising_pybars_behaviour_is_kept(self):
        for source, expected in [
            # An unclosed tag at the end of a template is dropped without an error.
            ('abc {{foo', "result.append('abc ')"),
            # CRLF at the start of a text run compiles as "\n".
            ('\r\nx', "result.append('\\n')"),
            # A subexpression's helper name joins its path segments.
            ('{{foo (a.b x)}}', 'resolve_subexpr(helpers, "ab", context'),
            # Path segments are pasted into the generated code without escaping.
            ("{{a.[b'c]}}", "u'b'c'"),
        ]:
            with self.subTest(source=source):
                self.assertIn(expected, pybars_rs.precompile(source))

    def test_surprising_pybars_errors_are_kept(self):
        for source, message in [
            # The line number is the number of lines of the whole template.
            ('line1\nline2 {{/x}}\nline3', 'Error at character 9 of line 3 near {{/x}}'),
            # Keyword argument names need two or more characters.
            ('{{foo a=1}}', 'Error at character 7 of line 1 near a=1}}'),
            # An argument that starts with a literal is that literal.
            ('{{foo trueish}}', 'Error at character 13 of line 1 near trueish}}'),
            ('{{foo 12abc}}', 'Error at character 8 of line 1 near 12abc}}'),
        ]:
            with self.subTest(source=source):
                with self.assertRaises(pybars.PybarsError) as raised:
                    pybars_rs.precompile(source)
                self.assertEqual(str(raised.exception), message)

    @unittest.skipUnless(IS_0_9_7, 'whitespace control is pybars3 0.9.7')
    def test_whitespace_control_is_kept(self):
        render = pybars_rs.Compiler().compile('a {{~b~}} c\n  {{#if d}}\n e\n  {{/if}}\n')
        self.assertEqual(str(render({'b': 'B', 'd': True})), 'aBc\n e\n')
        # The error is in the text that whitespace control produced.
        with self.assertRaises(pybars.PybarsError) as raised:
            pybars_rs.precompile('{{a}}\n  {{~b}')
        self.assertEqual(str(raised.exception), 'Error at character 8 of line 1 near {{b}')
