"""pybars_rs is a drop-in for pybars: the same names, the same Compiler, the same results.

The comparisons with pybars on many templates are in the other test modules.
"""

import contextlib
import hashlib
import inspect
import io
import os
import platform
import subprocess
import sys
import tempfile
import threading
import types
import unicodedata
import unittest
from unittest import mock

import pybars
import pybars._compiler
import pybars_rs
from pybars_rs import _native
import pymeta.runtime

TEMPLATES = [
    'hello {{name}}',
    '{{#if a}}\n  {{b.c}}\n{{else}}none{{/if}}',
    '{{#each xs}}{{@index}}: {{this}}{{/each}}',
    '{{> part aa=1 bb="x"}}',
    '{{{{raw}}}}{{x}}{{{{/raw}}}}{{! comment }}{{&html}}',
    'caf\u00e9 \u2028 {{x}} \U0001f600',
    'a\ud800b {{x}}',
    '{{x.[a\ud800]}}',
]

CONTEXT = {'name': 'world', 'a': True, 'b': {'c': '<c>'}, 'xs': ['p', 'q'], 'html': '<b>', 'x': 1}

DEEP = '{{#if a}}' * 30 + '{{/if}}' * 30


def outcome(call):
    try:
        return ('ok', call())
    except Exception as error:  # the class and message are the result
        return (type(error), str(error))


def run_python(script, **environment):
    environment = dict(os.environ, PYTHONWARNINGS='ignore', **environment)
    subprocess.run([sys.executable, '-c', script], check=True, env=environment)


class TestApi(unittest.TestCase):

    def test_the_rust_compiler_is_used_here(self):
        self.assertTrue(pybars_rs.is_available(), pybars_rs.unavailable_reason())
        self.assertIsNone(pybars_rs.unavailable_reason())
        before = pybars_rs.counters()['fast_path']
        pybars_rs.Compiler().precompile('hello {{name}}')
        self.assertEqual(pybars_rs.counters()['fast_path'], before + 1)

    def test_the_package_exports_pybars_runtime_names(self):
        self.assertLessEqual(set(pybars.__all__), set(pybars_rs.__all__))
        for name in set(pybars.__all__) - {'Compiler'}:
            self.assertIs(getattr(pybars_rs, name), getattr(pybars, name), name)
        self.assertIn(pybars.__version__, pybars_rs.PYBARS_VERSIONS)
        self.assertEqual(pybars_rs.__version__, _native.__version__)
        self.assertIn(unicodedata.unidata_version, pybars_rs.UNICODE_VERSIONS)

    def test_compiler_has_the_pybars_interface(self):
        self.assertTrue(issubclass(pybars_rs.Compiler, pybars.Compiler))
        # pybars_rs has its own code builder (see test_fallbacks_leave_pybars_state_alone).
        self.assertIsNot(pybars_rs.Compiler._builder, pybars.Compiler._builder)
        self.assertIs(type(pybars_rs.Compiler._builder), type(pybars.Compiler._builder))
        # The same compile grammar, but whose actions use pybars_rs' builder.
        ours, theirs = pybars_rs.Compiler._compiler, pybars.Compiler._compiler
        self.assertEqual(ours.__bases__, (theirs,))
        self.assertFalse({name for name in vars(ours) if name.startswith('rule_')})
        self.assertEqual(
            {key: value for key, value in ours.globals.items() if key != '__builtins__'},
            dict({key: value for key, value in theirs.globals.items() if key != '__builtins__'},
                 builder=pybars_rs.Compiler._builder),
        )
        for name, member in inspect.getmembers(pybars.Compiler):
            if name.startswith('__') or name in ('_generate_code', '_builder', '_compiler'):
                continue
            if inspect.isfunction(member):
                self.assertEqual(inspect.signature(getattr(pybars_rs.Compiler, name)), inspect.signature(member), name)
            else:
                self.assertIs(getattr(pybars_rs.Compiler, name), member, name)
        compiler = pybars_rs.Compiler()
        self.assertEqual(compiler._helpers, {})
        self.assertEqual(compiler.template_counter, 1)
        self.assertIsInstance(compiler._generate_code('{{a}}'), pybars._compiler.FunctionContainer)

    def test_precompile_matches_pybars(self):
        for source in TEMPLATES:
            with self.subTest(source=source):
                expected = pybars.Compiler().precompile(source)
                self.assertEqual(pybars_rs.Compiler().precompile(source), expected)
                self.assertEqual(pybars_rs.precompile(source), expected)

    def test_compiled_templates_render_like_pybars(self):
        partials = {'part': pybars.Compiler().compile('[{{aa}}|{{bb}}]')}
        for source in TEMPLATES[:6]:
            with self.subTest(source=source):
                ours = pybars_rs.Compiler().compile(source)
                theirs = pybars.Compiler().compile(source)
                self.assertEqual(ours.__name__, 'render')
                self.assertEqual(theirs.__name__, 'render')
                self.assertEqual(
                    outcome(lambda: str(ours(CONTEXT, partials=partials))),
                    outcome(lambda: str(theirs(CONTEXT, partials=partials))),
                )

    def test_compile_registers_modules_like_pybars(self):
        # pybars names the module after the first free `template_counter` value.
        for compiler in (pybars_rs.Compiler(), pybars.Compiler()):
            render = compiler.compile('{{a}}')
            self.assertEqual(render.__module__, 'pybars._templates._template_%d' % compiler.template_counter)
            self.assertIs(sys.modules[render.__module__].render, render)

        # A `path` names the module; pybars3 0.9.6 raises UnboundLocalError
        # instead while that module does not exist yet.
        def named(compiler, path):
            return outcome(lambda: compiler().compile('{{a}}', path=path).__module__)

        for path in ('pybars_rs_test/fresh', 'pybars_rs_test\\other'):
            with self.subTest(path=path):
                expected = named(pybars.Compiler, path)
                if expected[0] == 'ok':
                    del sys.modules[expected[1]]
                self.assertEqual(named(pybars_rs.Compiler, path), expected)
        sys.modules['pybars._templates.pybars_rs_test_taken'] = sys.modules[__name__]
        try:
            named_module = pybars_rs.Compiler().compile('{{a}}', path='pybars_rs_test/taken').__module__
        finally:
            del sys.modules['pybars._templates.pybars_rs_test_taken']
        self.assertTrue(named_module.startswith('pybars._templates.pybars_rs_test_taken_'))

    def test_template_runs_precompiled_source(self):
        code = pybars_rs.Compiler().precompile('Hi {{name}}')
        self.assertEqual(
            pybars_rs.Compiler().template(code)({'name': 'x'}),
            pybars.Compiler().template(code)({'name': 'x'}),
        )

    def test_errors_are_pybars_errors(self):
        for source in [
            '{{value}\nmore',
            '{{foo \u00b2}}',
            '{{#if a}}x{{/each}}',
            '{{foo ' + '1' * 4301 + '}}',
            '{{> p 1 2}}',
            b'bytes',
            None,
        ]:
            with self.subTest(source=source):
                expected = outcome(lambda: pybars.Compiler().precompile(source))
                self.assertNotEqual(expected[0], 'ok')
                self.assertEqual(outcome(lambda: pybars_rs.Compiler().precompile(source)), expected)

    def test_syntax_errors_take_the_fast_path(self):
        before = pybars_rs.counters()
        with self.assertRaisesRegex(pybars.PybarsError, r'^Error at character 7 of line 2 near \{\{value\}$'):
            pybars_rs.Compiler().precompile('{{value}\nmore')
        self.assertEqual(pybars_rs.counters()['fast_path'], before['fast_path'] + 1)

    def test_fallbacks_are_counted_by_reason(self):
        class Text(str):
            __slots__ = ()

        before = pybars_rs.counters()
        for source in [b'x', Text('{{x}}'), '{{foo \u00b2}}', 'a\ud800b', DEEP]:
            outcome(lambda: pybars_rs.Compiler().precompile(source))
        after = pybars_rs.counters()
        self.assertEqual(after['not_str'], before['not_str'] + 2)
        self.assertEqual(after['int_conversion'], before['int_conversion'] + 1)
        self.assertEqual(after['surrogates'], before['surrogates'] + 1)
        self.assertEqual(after['nesting_depth'], before['nesting_depth'] + 1)
        self.assertEqual(after['fast_path'], before['fast_path'])

    def test_the_int_digit_limit_is_read_on_every_call(self):
        source = '{{foo ' + '1' * 5000 + '}}'
        previous = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(0)
            self.assertEqual(pybars_rs.precompile(source), pybars.Compiler().precompile(source))
            before = pybars_rs.counters()['fast_path']
            pybars_rs.precompile(source)
            self.assertEqual(pybars_rs.counters()['fast_path'], before + 1)
            sys.set_int_max_str_digits(4999)
            self.assertEqual(
                outcome(lambda: pybars_rs.precompile(source)),
                outcome(lambda: pybars.Compiler().precompile(source)),
            )
        finally:
            sys.set_int_max_str_digits(previous)

    def test_the_debug_flag_runs_pybars(self):
        with mock.patch.object(pybars._compiler, 'debug', True):
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                expected = pybars.Compiler().precompile('{{a}}')
            self.assertTrue(printed.getvalue())
            before = pybars_rs.counters()['debug']
            with contextlib.redirect_stdout(io.StringIO()) as printed_again:
                self.assertEqual(pybars_rs.Compiler().precompile('{{a}}'), expected)
            self.assertEqual(printed_again.getvalue(), printed.getvalue())
            self.assertEqual(pybars_rs.counters()['debug'], before + 1)

    def test_precompile_is_thread_safe(self):
        templates = ['{{#if a}}{{#each b}}{{name}}{{/each}}{{else}}none{{/if}} ' * 20, '{{foo \u00b2}}', '{{#if a}}' * 25]
        expected = [outcome(lambda: pybars.Compiler().precompile(source)) for source in templates]
        results, errors = [], []

        def work():
            try:
                compiler = pybars_rs.Compiler()
                for _ in range(30):
                    results.append([outcome(lambda: compiler.precompile(source)) for source in templates])
            except Exception as error:  # collected for the assert
                errors.append(error)

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(len(results), 240)
        self.assertTrue(all(result == expected for result in results))

    def test_the_environment_guard(self):
        self.assertEqual(pybars_rs._environment(), (pybars.__version__, None))
        for target, attribute, value, reason in [
            (platform, 'python_implementation', lambda: 'PyPy', 'on CPython, not PyPy'),
            (unicodedata, 'unidata_version', '12.1.0', 'no character tables for Unicode 12.1.0'),
            (pybars, '__version__', '0.0.1', 'pybars is version 0.0.1'),
        ]:
            with self.subTest(reason=reason), mock.patch.object(target, attribute, value):
                version, problem = pybars_rs._environment()
                self.assertIsNone(version)
                self.assertIn(reason, problem)

    def test_modified_sources_disable_the_rust_compiler(self):
        with mock.patch.dict(pybars_rs._PYBARS_COMPILERS, clear=True):
            self.assertIn('pybars._compiler differs', pybars_rs._environment()[1])
        with mock.patch.dict(pybars_rs._PYMETA_SOURCES, {pymeta.runtime: '0' * 64}):
            self.assertIn('pymeta.runtime differs', pybars_rs._environment()[1])

    def test_the_installed_pybars_has_a_verified_compiler(self):
        digest = pybars_rs._source_digest(pybars._compiler)
        self.assertEqual(pybars_rs._PYBARS_COMPILERS.get(digest), pybars.__version__, digest)

    def test_line_endings_do_not_change_the_digest(self):
        with open(pybars._compiler.__file__, 'rb') as source:
            unix = source.read().replace(b'\r\n', b'\n')
        with tempfile.TemporaryDirectory() as directory:
            for name, text in [('unix.py', unix), ('windows.py', unix.replace(b'\n', b'\r\n'))]:
                path = os.path.join(directory, name)
                with open(path, 'wb') as copy:
                    copy.write(text)
                with self.subTest(name=name):
                    module = types.SimpleNamespace(__file__=path)
                    self.assertEqual(pybars_rs._source_digest(module), pybars_rs._source_digest(pybars._compiler))

    def test_the_environment_variable_disables_the_rust_compiler(self):
        script = (
            'import pybars_rs, pybars\n'
            'assert not pybars_rs.is_available(), pybars_rs.unavailable_reason()\n'
            "assert 'PYBARS_RS_DISABLE' in pybars_rs.unavailable_reason()\n"
            "source = '{{#if a}}x{{/if}}'\n"
            'assert pybars_rs.precompile(source) == pybars.Compiler().precompile(source)\n'
            "assert pybars_rs.counters()['unavailable'] == 1, pybars_rs.counters()\n"
            "assert pybars_rs.counters()['fast_path'] == 0\n"
        )
        run_python(script, PYBARS_RS_DISABLE='1')

    def test_fallbacks_leave_pybars_state_alone(self):
        # Code that uses pybars directly relies on pybars' class-level builder,
        # behind its own lock; a pybars_rs fallback must never use it.
        def trap(*_args):
            raise AssertionError("pybars' shared CodeBuilder was used")

        deep = '{{#if a}}' * 30 + 'x' + '{{/if}}' * 30
        with mock.patch.object(pybars.Compiler._builder, 'start', trap):
            before = pybars_rs.counters()['nesting_depth']
            self.assertTrue(pybars_rs.Compiler().precompile(deep).endswith('    return result\n'))
            self.assertEqual(pybars_rs.counters()['nesting_depth'], before + 1)
            with self.assertRaisesRegex(ValueError, 'invalid literal'):
                pybars_rs.Compiler().precompile('{{foo \u00b2}}')

    def test_the_native_method_binds_like_a_function(self):
        self.assertIn('_generate_code', vars(pybars_rs.Compiler))
        self.assertIs(pybars_rs.Compiler._generate_code, pybars_rs._GENERATE_CODE)
        compiler = pybars_rs.Compiler()
        self.assertIs(compiler._generate_code.__self__, compiler)
        # Called on the class, as pybars' own code could.
        container = pybars_rs.Compiler._generate_code(compiler, '{{a}}')
        self.assertEqual(container.full_code, pybars.Compiler().precompile('{{a}}'))

    def test_the_self_check_leaves_pybars_state_alone(self):
        # It runs at import, possibly next to a thread compiling with pybars.
        def trap(*_args):
            raise AssertionError("pybars' shared CodeBuilder was used")

        with mock.patch.object(pybars.Compiler._builder, 'start', trap):
            self.assertIsNone(pybars_rs._self_check(pybars_rs._GENERATE_CODE, pybars.__version__))

    def test_the_extension_module_reports_the_port_alone(self):
        versions = {'pybars_version': pybars.__version__, 'unicode_version': unicodedata.unidata_version}
        self.assertEqual(_native.precompile('{{a}}', **versions), ('code', pybars.Compiler().precompile('{{a}}')))
        self.assertEqual(_native.precompile('{{a}', **versions), ('error', 'Error at character 3 of line 1 near {{a}', 3))
        self.assertEqual(_native.precompile('{{foo \u00b2}}', **versions), ('fallback', 'int_conversion'))
        self.assertEqual(_native.precompile('{{#if a}}x{{/if}}', nesting_limit=1, **versions), ('fallback', 'nesting_depth'))
        with self.assertRaisesRegex(ValueError, 'unsupported Unicode version'):
            _native.precompile('', pybars_version=pybars.__version__, unicode_version='1.0.0')
        with self.assertRaisesRegex(ValueError, 'unsupported pybars3 version'):
            _native.precompile('', pybars_version='0.9.5', unicode_version=unicodedata.unidata_version)
        header = _native.HEADERS[pybars.__version__]
        self.assertEqual(pybars_rs.precompile('')[:len(header)], header)
        self.assertEqual(sorted(_native.HEADERS), sorted(pybars_rs.PYBARS_VERSIONS))

    def test_the_self_check_digests_are_pybars_output(self):
        digests = pybars_rs._SELF_CHECK[pybars.__version__]
        for template, digest in zip(pybars_rs._SELF_CHECK_TEMPLATES, digests):
            with self.subTest(template=template):
                code = pybars.Compiler().precompile(template)
                self.assertEqual(hashlib.sha256(code.encode('utf-8')).hexdigest(), digest)

    def test_importing_pybars_rs_builds_no_pymeta_grammar(self):
        # Building one costs 70 ms and recurses deeply; pybars_rs' fallbacks
        # reuse pybars' own compile grammar with builders of their own instead.
        script = (
            'import pybars, pymeta.grammar\n'
            'built = []\n'
            'make = pymeta.grammar.OMeta.makeGrammar.__func__\n'
            'pymeta.grammar.OMeta.makeGrammar = classmethod(lambda cls, *a, **k: built.append(a) or make(cls, *a, **k))\n'
            'import pybars_rs\n'
            "assert pybars_rs.precompile('{{#if a}}' * 25 + '{{/if}}' * 25)\n"
            "assert pybars_rs.counters()['nesting_depth'] == 1, pybars_rs.counters()\n"
            'assert not built, len(built)\n'
        )
        run_python(script)

    def test_a_fallback_can_compile_from_inside_another(self):
        # pybars3 0.9.6 iterates a str subclass and calls len() on it, and
        # pybars3 0.9.7 calls `whitespace_control`, either of which may compile
        # templates; ones that need pybars too (here: a lone surrogate and deep
        # nesting) must not wait for the outer call, nor share its code builder.
        def compile_reentrantly(compiler_class):
            seen = []

            def nested(source):
                seen.append(outcome(lambda: compiler_class().precompile(source)))

            class Template(str):
                __slots__ = ()

                def __iter__(self):
                    nested('a\ud800b {{x}}')
                    return super().__iter__()

                def __len__(self):
                    nested('{{#if a}}' * 25 + '{{/if}}' * 25)
                    return super().__len__()

            class Reentrant(compiler_class):
                def whitespace_control(self, source):
                    nested('a\ud800b {{x}}')
                    nested('{{#if a}}' * 25 + '{{/if}}' * 25)
                    return super().whitespace_control(source)

            seen.append(outcome(lambda: Reentrant().precompile(Template('{{#each xs}}{{this}}{{/each}}'))))
            return seen

        expected = compile_reentrantly(pybars.Compiler)
        results = []
        thread = threading.Thread(target=lambda: results.append(compile_reentrantly(pybars_rs.Compiler)), daemon=True)
        thread.start()
        thread.join(timeout=60)
        self.assertFalse(thread.is_alive(), 'a nested fallback deadlocked')
        self.assertEqual(results, [expected])
        self.assertEqual([result[0] for result in expected], ['ok', 'ok', 'ok'])

    def test_counters_name_every_reason(self):
        self.assertEqual(set(pybars_rs.counters()), {
            'fast_path',
            'unavailable',
            'debug',
            'not_str',
            'surrogates',
            'int_conversion',
            'nesting_depth',
            'panic',
            'internal',
        })
