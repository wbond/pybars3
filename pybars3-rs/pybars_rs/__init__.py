"""pybars3's template compiler, running on Rust.

``pybars_rs.Compiler`` is a drop-in replacement for ``pybars.Compiler``:
``compile()``, ``precompile()`` and ``template()`` return what pybars returns,
byte for byte, and raise what pybars raises, but compiling a template is one to
two orders of magnitude faster, releases the GIL, and is safe from several
threads at once::

    import pybars_rs

    render = pybars_rs.Compiler().compile(u"Hello {{name}}!")
    render({'name': 'world'})  # u'Hello world!'
    source = pybars_rs.precompile(u"Hello {{name}}!")  # pybars' generated module

``pybars_rs.Compiler`` subclasses ``pybars.Compiler`` and replaces one method,
``_generate_code``, which turns template text into Python source. The code it
generates still imports pybars' runtime, so pybars3 stays installed, and
``pybars_rs`` re-exports pybars' runtime names (``PybarsError``, ``Scope``,
``strlist``, ``log``) so that ``import pybars_rs as pybars`` works.

When reproducing pybars needs Python itself (an integer literal that ``int()``
rejects, a template nested deeply enough to reach the recursion limit, a
string with lone surrogates, ``pybars._compiler.debug``), the call runs
pybars' own ``_generate_code`` instead, from native code so that it sees the
same Python stack. ``counters()`` reports how often that happens.

The Rust compiler is only used with the pybars3 and PyMeta3 sources it was
verified against, on CPython with a supported Unicode database. Anywhere
else, or with ``PYBARS_RS_DISABLE=1`` in the environment, ``Compiler`` is
pybars' compiler and ``unavailable_reason()`` says why.
"""

import contextvars
import hashlib
import os
import platform
import types
import unicodedata

import pybars
from pybars import PybarsError, Scope, log, strlist
import pybars._compiler
import pymeta.boot
import pymeta.builder
import pymeta.grammar
import pymeta.runtime

from pybars_rs import _native

__version__ = _native.__version__

#: The pybars3 releases whose compiler pybars_rs reproduces.
PYBARS_VERSIONS = _native.PYBARS_VERSIONS

#: The Unicode database versions (``unicodedata.unidata_version``) that
#: pybars_rs has character tables for.
UNICODE_VERSIONS = _native.UNICODE_VERSIONS

__all__ = [
    'Compiler',
    'log',
    'strlist',
    'Scope',
    'PybarsError',
    'PYBARS_VERSIONS',
    'UNICODE_VERSIONS',
    'counters',
    'is_available',
    'precompile',
    'unavailable_reason',
    ]

#: SHA-256 of each ``pybars/_compiler.py`` that the Rust compiler was verified
#: against, and the pybars3 release whose compiler it has. A change to that
#: file disables the Rust compiler until its digest is added here, after the
#: tests have shown that the compiler still gives pybars' output.
_PYBARS_COMPILERS = {
    # pybars3 0.9.6 and 0.9.7, as released.
    '01dc4c57a1fd335078c4ddbefa70cf220ae4e64f8e5aed756cf1688dc2aa67d1': '0.9.6',
    '0ff0e33162b377a6965219a09d4d76c2d507f3e179fd83412a762aa7f0e392b3': '0.9.7',
    # The master branch after 0.9.7, which changed the runtime only.
    'cb8cb7c7634e3d040b5853c9dc1283e329facfa72334ce082314e42971741e6b': '0.9.7',
}

#: SHA-256 of the PyMeta3 0.5.1 sources that run pybars' grammars: its runtime
#: and the grammar compiler that pybars builds its grammars with.
_PYMETA_SOURCES = {
    pymeta.boot: 'e7b618fdd68497748cab4526960de12b6eacdaa5201ae578b506b9b386342546',
    pymeta.builder: '3d6c61ff24a095aa9e0a01a7d67667dcc6de431d25b56521d72ef9225de4ea5c',
    pymeta.grammar: '38d02d49264ed8af7670868d29d65f78464a1ca92724bfa89cf6957a172ca2da',
    pymeta.runtime: 'f68e56e797a372c5f353e4c91175ed991dd7ead85f68ff1f70317fb6ae7f3b4c',
}

_SELF_CHECK_TEMPLATES = [
    u'Hello {{name}}!',
    u'{{#if a}}\n  x {{b.c}}\n{{else}}y{{/if}}{{^d}}z{{/d}}',
    u'{{#each xs}}{{this}} {{@index}} {{../y}}{{/each}}',
    u'{{> part aa=1 bb="s"}}{{foo (bar baz=true) null -12}}',
    u'{{{{raw}}}}{{x}}{{{{/raw}}}}{{! note }}{{&y}}{{{z}}}',
    u'caf\u00e9 \u2028 {{x.[a b]}} \U0001f600',
    # Whitespace control, which pybars3 0.9.6 rejects.
    u'a {{~b~}}\n  {{#if c}}\n d\n  {{/if}}\n',
]

#: Compiled at import, with the SHA-256 of pybars' output for each (the same on
#: every supported CPython): any difference disables the Rust compiler. pybars'
#: sources are pinned above, so its output is known without running it.
_SELF_CHECK = {
    '0.9.6': [
        '4ec2d2ada4f63949766f0c89178675ab5962667260311b77d5f976b717eeee29',
        '00906096469ebe979bae8770cdc1357f1999d9d5a8b4421e663b2489ea8ed036',
        '6e4be28afcaa3b61ea71ae4503e36b797ebc06956d6e7293d9466a0dc094b8da',
        'a8f6062cfebc75ea3c00f85049283708a6aaf481e7ca8276a0466040a8ce0021',
        '3a45673643e23f3fa1ccf97a2936347b9152e9a1e211a8c7fc32c931b19d1432',
        '77042c13863641756dc3e4f55567b2a4ce12e0d8ccf47217517317a13c91549f',
    ],
    '0.9.7': [
        '26b1fc7eb935a4f39ce1fb887a6ef66224d4310c35764e3a96308fb5fb75b269',
        'e57f121ae06a9a9f4ffaf0b65f3d9d74c8d55af678148508268b37b48a4b2f17',
        '5b589f808a597ef25ab5e605a906d966bfcf40c1a78b5159c39122ae5fd896aa',
        '3c2cb4ec8f546b6c3e40e0aceeb2d5f549a9734f2d7eee09f2c173910c9396b5',
        '290f8223715bbbc93c458dce2db4b56b0041c2ed137b446a84731bd14e48fd5e',
        '41163c5bcaedee1c251ede347f557981a5770166a676b14d3f74311c8456234c',
        'ed0021e2ed332c131cba81b4ca61afce8e8119bf953d748ff52c97233330af7c',
    ],
}


def _source_digest(module):
    """
    The SHA-256 of a module's source file, with Unix line endings: Python reads
    source files with universal newlines, so a checkout with Windows line
    endings runs the same code

    :param module:
        A module loaded from a source file

    :return:
        The digest as a hex string
    """

    with open(module.__file__ or '', 'rb') as source:
        return hashlib.sha256(source.read().replace(b'\r\n', b'\n')).hexdigest()


def _environment():
    """
    Checks whether the Rust compiler reproduces the installed pybars, in this
    interpreter

    :return:
        A tuple of (version, problem): the pybars3 release whose compiler is
        installed, and why the Rust compiler must not be used, or None
    """

    if os.environ.get('PYBARS_RS_DISABLE', '') not in ('', '0'):
        return None, 'disabled by the PYBARS_RS_DISABLE environment variable'
    if platform.python_implementation() != 'CPython':
        return None, 'pybars_rs reproduces pybars on CPython, not %s' % platform.python_implementation()
    if unicodedata.unidata_version not in UNICODE_VERSIONS:
        return None, 'pybars_rs has no character tables for Unicode %s' % unicodedata.unidata_version
    try:
        digest = _source_digest(pybars._compiler)
        version = _PYBARS_COMPILERS.get(digest)
        if version is None:
            return None, 'pybars._compiler differs from the files pybars_rs was verified against (its SHA-256 is %s)' % digest
        for module, digest in _PYMETA_SOURCES.items():
            if _source_digest(module) != digest:
                return None, '%s differs from the PyMeta3 0.5.1 file pybars_rs was verified against' % module.__name__
    except OSError as error:
        return None, 'cannot read the sources of pybars and PyMeta3: %s' % error
    if pybars.__version__ != version:
        return None, 'pybars is version %s, but its compiler is the one of pybars3 %s' % (pybars.__version__, version)
    return version, None


# pybars keeps one code builder on its class, shared by every compile in the
# process, which is why pybars itself is not thread-safe. When pybars_rs runs
# pybars' `_generate_code`, it gives the call a code builder of its own: a
# subclass of pybars' compile grammar whose `globals`, where PyMeta looks up
# `builder` when it runs the grammar's actions, holds a new CodeBuilder. That
# costs a class, not a PyMeta grammar build (which takes 70 ms and recurses
# deeply), so fallbacks need no lock: they can run in several threads at once,
# and nest, as when a str subclass compiles a template while pybars parses it.

def _new_compile_grammar():
    """
    pybars' compile grammar, with a code builder of its own

    :return:
        A subclass of ``pybars.Compiler._compiler``
    """

    base = pybars.Compiler._compiler
    namespace = {
        '__module__': base.__module__,
        'globals': dict(base.globals or {}, builder=pybars._compiler.CodeBuilder()),
    }
    return type(base.__name__, (base,), namespace)


# For calls to pybars' `_generate_code` with a pybars_rs.Compiler outside a
# fallback, such as tests.
_COMPILE_GRAMMAR = _new_compile_grammar()
_BUILDER = _COMPILE_GRAMMAR.globals['builder']

# The compile grammar of the fallback running in this context: the native
# `_generate_code` sets it around each call to pybars' own.
_FALLBACK_GRAMMAR = contextvars.ContextVar('pybars_rs_fallback_grammar', default=None)


class _CompileGrammar:

    """
    ``Compiler._compiler``, which pybars' ``_generate_code`` reads: the
    current fallback's grammar, or pybars_rs' default one
    """

    __slots__ = ()

    def __get__(self, instance, owner=None):
        grammar = _FALLBACK_GRAMMAR.get()
        return _COMPILE_GRAMMAR if grammar is None else grammar


def _generate_code(pybars_version, unicode_version):
    return _native.GenerateCode(
        original=pybars.Compiler._generate_code,
        function_container=pybars._compiler.FunctionContainer,
        compiler_module=pybars._compiler,
        error_class=PybarsError,
        new_compile_grammar=_new_compile_grammar,
        fallback_grammar=_FALLBACK_GRAMMAR,
        pybars_version=pybars_version,
        unicode_version=unicode_version,
    )


def _self_check(generate_code, version):
    """
    Compiles a few templates with the Rust compiler alone

    :param generate_code:
        The native ``_generate_code``

    :param version:
        The pybars3 release whose compiler is installed

    :return:
        Why the Rust compiler disagrees with pybars on them, or None
    """

    for template, digest in zip(_SELF_CHECK_TEMPLATES, _SELF_CHECK[version]):
        try:
            result = generate_code.try_fast_path(template)
        except Exception as error:  # any failure means "use pybars"
            return 'a self-check template raised %s: %s' % (type(error).__name__, error)
        if isinstance(result, str):
            return 'a self-check template fell back to pybars (%s)' % result
        if hashlib.sha256(result.full_code.encode('utf-8')).hexdigest() != digest:
            return 'a self-check template compiled differently from pybars'
    return None


def _build():
    version, problem = _environment()
    if problem is None:
        generate_code = _generate_code(version, unicodedata.unidata_version)
        problem = _self_check(generate_code, version)
        if problem is None:
            return generate_code, None
    return _generate_code(None, None), problem


_GENERATE_CODE, _UNAVAILABLE_REASON = _build()


class _NativeMethod:

    """
    Binds a native callable as a method.

    A Python function would add a frame to every call. The bound method that
    ``types.MethodType`` returns calls the native code directly, so pybars'
    ``_generate_code`` runs at the stack depth it would have had without
    pybars_rs when a call falls back, and raises ``RecursionError`` exactly
    when pybars would.
    """

    __slots__ = ('_function',)

    def __init__(self, function):
        self._function = function

    def __get__(self, instance, owner=None):
        if instance is None:
            # `Compiler._generate_code(compiler, source)` works as with pybars.
            return self._function
        return types.MethodType(self._function, instance)


class Compiler(pybars.Compiler):

    """
    ``pybars.Compiler``, with its template compiler running on Rust.

    ``compile()``, ``precompile()`` and ``template()`` are pybars' own; only
    ``_generate_code``, which turns template text into Python source, is
    replaced.
    """

    _builder = _BUILDER
    _compiler = _CompileGrammar()
    _generate_code = _NativeMethod(_GENERATE_CODE)


def precompile(source):
    """
    Generates the Python module that pybars generates for a template, as
    ``Compiler().precompile(source)`` does

    :param source:
        The template source as a unicode string

    :return:
        Python source code that can be saved to a file
    """

    return Compiler().precompile(source)


def is_available():
    """
    :return:
        Whether ``Compiler`` uses the Rust compiler; when not, it is pybars'
    """

    return _UNAVAILABLE_REASON is None


def unavailable_reason():
    """
    :return:
        Why ``Compiler`` does not use the Rust compiler, or None when it does
    """

    return _UNAVAILABLE_REASON


def counters():
    """
    Counts the compiles that the Rust compiler answered (``fast_path``), and
    the ones that ran pybars, by reason: ``unavailable`` (the Rust compiler is
    disabled, see ``unavailable_reason()``), ``debug``, ``not_str``,
    ``surrogates``, ``int_conversion``, ``nesting_depth``, and ``panic`` and
    ``internal``, which mean a bug in pybars_rs that running pybars hid: please
    report them.

    :return:
        A dict of counts by name
    """

    return dict(_GENERATE_CODE.counters())
