"""Mutants of pybars: changes that the comparison harness must notice.

Each mutant replaces a piece of pybars' source and is compiled in memory, so
pybars itself is never modified. ``test_harness.py`` requires its seed
template to expose every mutant whose target is in the installed pybars:
some are specific to pybars3 0.9.6 or 0.9.7.
"""

import contextlib
import pathlib
import types
import warnings

import pybars
import pybars._compiler

#: (source text, replacement, the seed that exposes it, what it changes)
PYBARS_MUTANTS = [
    (
        "line_num = source.count('\\n') + 1",
        "line_num = source.count('\\n', 0, position) + 1",
        '{{value}\nmore\nlines',
        'the line number counts every newline in the text, not the ones before the error',
    ),
    (
        "space ::= ' '|'\\t'|'\\r'|'\\n'",
        "space ::= ' '",
        '{{#if\ta}}x{{/if}}',
        'a tab separates the block symbol from its argument',
    ),
    (
        "    | '\\\\' => '\\\\\\\\'\n    | (~(\"'\") <anything>)",
        '    | (~("\'") <anything>)',
        "{{foo ab='x\\\\y'}}",
        'a backslash inside a single-quoted string',
    ),
    (
        "symbol ::=  ~<alt_inner> '['? (<letterOrDigit>|'-'|'@')+",
        "symbol ::=  ~<alt_inner> '['? (<letterOrDigit>|'@')+",
        '{{a-b}}',
        'a dash is part of a symbol',
    ),
    (
        "integer ::= '-'?:sign",
        'integer ::= :sign',
        '{{foo x=-12}}',
        'a negative integer literal',
    ),
    (
        "newline_text ::= (~(<start>) ('\\r'?'\\n'):char)",
        "newline_text ::= (~(<start>) ('\\n'):char)",
        '{{x}}\r\n',
        'a CRLF after a tag produces a newline node',
    ),
    # pybars3 0.9.6
    (
        "boundry = re.search('{{|{|\\s|$', source[:position][::-1])",
        "boundry = re.search('{{|\\s|$', source[:position][::-1])",
        '{{#if a}}x{{else}y{{/if}}',
        'the error word stops at a `{` boundary',
    ),
    (
        '                    child_tree.pop(1)  # trailing newline',
        '                    pass',
        '{{#if a}}\nbody\n{{/if}}\n',
        'a standalone block tag loses the newline after it',
    ),
    # pybars3 0.9.7
    (
        "boundry = re.search(r'{{|{|\\s|$', source[:position][::-1])",
        "boundry = re.search(r'{{|\\s|$', source[:position][::-1])",
        '{{#if a}}x{{else}y{{/if}}',
        'the error word stops at a `{` boundary',
    ),
    (
        "r'~}}\\s*|\\s*{{~|'",
        "r'~}}|\\s*{{~|'",
        '{{a~}}  \n b',
        'a `~` before `}}` removes the whitespace after the tag',
    ),
    (
        "r'(?<=\\n)([ \\t]*{{(#[^{}]+|/[^{}]+|![^{}]+|else|else if [^{}]+)}}[ \\t]*)+\\r?\\n|'",
        "r'(?<=\\n)([ \\t]*{{(#[^{}]+|/[^{}]+|![^{}]+|else if [^{}]+)}}[ \\t]*)+\\r?\\n|'",
        'x\n{{#if a}}\n{{else}}\ny{{/if}}',
        'a line that holds only `{{else}}` is removed',
    ),
    (
        "r'\\r?\\n([ \\t]*{{(/[^{}]+|![^{}]+)}}[ \\t]*)+$',",
        "r'\\r?\\n([ \\t]*{{(/[^{}]+|![^{}]+)}}[ \\t]*)+\\Z',",
        'a\n{{/b}}\n',
        '`$` matches before a final newline',
    ),
    (
        "lambda match: cleanup_sub('', match.group(0).strip())",
        "lambda match: cleanup_sub('', match.group(0))",
        'a \t\n {{~b}}',
        'the whitespace of a match is stripped',
    ),
    (
        "r'(?<={{)~|~(?=}})|(?<=}})[ \\t]+(?={{)'",
        "r'(?<={{)~|~(?=}})'",
        'x\n  {{#a}} {{#b}} \r\ny{{/b}}{{/a}}',
        'the blanks between the tags of a line are removed',
    ),
]


def pristine_source():
    with open(pybars._compiler.__file__ or '', encoding='utf-8') as source:
        return source.read()


def applicable_mutants():
    """The mutants whose target is in the installed pybars."""
    pristine = pristine_source()
    return [mutant for mutant in PYBARS_MUTANTS if mutant[0] in pristine]


@contextlib.contextmanager
def mutated_pybars(from_text, to_text):
    """Replace ``pybars.Compiler`` with one compiled, in memory, from mutated source."""
    path = pathlib.Path(pybars._compiler.__file__ or '')
    pristine = pristine_source()
    if from_text not in pristine:
        raise LookupError('mutant target not found in pybars._compiler: %r' % from_text)
    mutant = types.ModuleType('pybars._compiler_mutant')
    mutant.__file__ = str(path)
    mutant.__package__ = 'pybars'
    with warnings.catch_warnings():
        # pybars3 0.9.6 has '\s' and '\w' in plain string literals.
        warnings.simplefilter('ignore', SyntaxWarning)
        code = compile(pristine.replace(from_text, to_text, 1), str(path), 'exec')
    exec(code, mutant.__dict__)
    original = pybars.Compiler
    pybars.Compiler = mutant.Compiler
    try:
        yield
    finally:
        pybars.Compiler = original
