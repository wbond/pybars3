"""The characters that pybars and pybars_rs can tell apart, derived from pybars' grammars.

pybars looks at a template character in only these ways: equality with a
grammar literal or with a literal of the regular expressions of pybars3
0.9.7's whitespace control, the ``str`` predicates of PyMeta's built-in rules
(``letter``: ``isalpha``, ``digit``: ``isdigit``, ``letterOrDigit``:
``isalnum`` or ``_``, ``spaces``: ``isspace``, also ``\\s`` and ``strip()``),
``int()``, which needs decimal digits, and ``repr()``, which escapes what
``isprintable`` rejects in one of three forms depending on the code point.
pybars_rs also handles ASCII, non-ASCII and lone surrogates differently. Two characters with the same answers to all of these
take the same path through both, which only copy them into the output. So
templates over one representative of each class, plus a second plain letter
for names that must differ (``{{#b}}...{{/c}}``), stand for every template of
the same length.
"""

from collections import defaultdict
import functools
import sys

import pybars._compiler
from pymeta.builder import TreeBuilder
from pymeta.grammar import OMeta

# Literals of the compile grammar that a path segment, which is template text,
# is compared with.
SEGMENT_LITERALS = ('this', '/', '.')

# Literals of the regular expressions of pybars3 0.9.7's
# Compiler.whitespace_control, which runs before the grammar.
WHITESPACE_CONTROL_LITERALS = ('~', '{{', '}}', '#', '/', '!', 'else', 'else if ', ' ', '\t', '\r', '\n')


def _literals(tree, found):
    if not isinstance(tree, (list, tuple)) or not tree:
        return
    if not isinstance(tree[0], str):
        for child in tree:
            _literals(child, found)
        return
    if tree[0] == 'Exactly':
        found.add(str(tree[1]))
    for child in tree[1:]:
        _literals(child, found)


def grammar_literals(text):
    found = set()
    _literals(OMeta.metagrammarClass(text).parseGrammar('g', TreeBuilder), found)
    return found


@functools.cache
def _literal_characters():
    found = {c for literal in grammar_literals(pybars._compiler.handlebars_grammar) for c in literal}
    others = SEGMENT_LITERALS + WHITESPACE_CONTROL_LITERALS
    return frozenset(found | {c for literal in others for c in literal})


def class_of(character):
    """What pybars and pybars_rs can observe of ``character``."""
    code_point = ord(character)
    return (
        character if character in _literal_characters() else None,
        character.isalpha(),
        character.isalnum(),
        character.isdigit(),
        character.isdecimal(),
        character.isspace(),
        character.isprintable(),
        0xD800 <= code_point <= 0xDFFF,
        code_point < 0x80,
        code_point <= 0xFF,
        code_point <= 0xFFFF,
    )


@functools.cache
def character_classes():
    """Every code point, grouped by ``class_of``."""
    classes = defaultdict(list)
    for code_point in range(sys.maxunicode + 1):
        character = chr(code_point)
        classes[class_of(character)].append(character)
    return dict(classes)


@functools.cache
def alphabet():
    """The lowest code point of each class, and a second plain letter."""
    representatives = {members[0] for members in character_classes().values()} | {'b'}
    return tuple(sorted(representatives, key=ord))
