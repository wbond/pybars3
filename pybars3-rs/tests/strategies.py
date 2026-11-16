"""Hypothesis strategies for Handlebars templates, shaped by pybars' grammar.

Templates are built from every construct of ``handlebars_grammar``: text,
mustaches, blocks with ``else``, inverted blocks, partials, raw blocks,
comments, subexpressions and every literal form, with the ``~`` marks and the
lines of block tags of pybars3 0.9.7's whitespace control. Names and text draw from the
character-class alphabet (``alphabet.py``), so that every class of character
reaches every construct. Half of the templates then get a few characters
inserted, deleted or replaced, which reaches syntax errors and the error
position logic. Hypothesis shrinks a failing template to a minimal one.
"""

from hypothesis import strategies as st

from tests import alphabet

ALPHABET = list(alphabet.alphabet())

NAME_CHARACTERS = ['a', 'b', 'e', 's', 't', 'h', 'i', '_', '-', '@', 'A', '0', '\u00aa', '\u0660', '\u00b2', '\u00bc']
KEYWORDS = ['if', 'each', 'with', 'unless', 'this', 'else', 'true', 'false', 'null', 'undefined', 'log', 'lookup']
SEGMENT_SPECIALS = ['..', '.', '/', '@index', '@key', '../', '@../', 'this']

any_character = st.sampled_from(ALPHABET)
spaces = st.text(st.sampled_from([' ', '\t', '\r', '\n', '\x0b', '\u0085', '\u00a0']), max_size=2)
separators = st.text(st.sampled_from([' ', '\t', '\r', '\n']), min_size=1, max_size=2)

names = st.one_of(st.text(st.sampled_from(NAME_CHARACTERS), min_size=1, max_size=4), st.sampled_from(KEYWORDS))
segments = st.one_of(
    names,
    st.text(any_character, max_size=4).map(lambda inner: f'[{inner}]'),
    st.sampled_from(SEGMENT_SPECIALS),
)
paths = st.builds(
    lambda first, rest: first + ''.join(rest),
    segments,
    st.lists(
        st.builds(lambda separator, segment: separator + segment, st.sampled_from(['.', '/']), segments), max_size=2
    ),
)

_string_bodies = st.text(
    st.sampled_from(['a', ' ', '\\', '\n', '\r', "'", '"', '{', '}', '\u00e9', '\u2028', '\ud800']), max_size=4
)
literals = st.one_of(
    _string_bodies.map(lambda body: f'"{body}"'),
    _string_bodies.map(lambda body: f"'{body}'"),
    st.builds(
        lambda sign, digits: sign + digits,
        st.sampled_from(['', '-']),
        st.text(st.sampled_from(['0', '1', '9', '\u0663', '\uff15', '\u00b2']), min_size=1, max_size=3),
    ),
    st.sampled_from(['true', 'false', 'null', 'undefined', '-', '1' * 4301]),
)


def arguments(values):
    keywords = st.builds(lambda key, value: f'{key}={value}', names, values)
    return st.lists(
        st.builds(lambda space, value: space + value, separators, st.one_of(values, keywords)), max_size=3
    ).map(''.join)


subexpressions = st.deferred(
    lambda: st.builds(
        lambda before, head, args, after: f'({before}{head}{args}{after})',
        spaces,
        paths,
        arguments(st.one_of(literals, paths, subexpressions)),
        spaces,
    )
)
values = st.one_of(literals, paths, subexpressions)


tildes = st.sampled_from(['', '', '~'])
line_ends = st.sampled_from(['\n', '\n', '\r\n', '  \n', ' \t\r\n'])


def mustaches(opening, closing):
    return st.builds(
        lambda left, before, path, args, after, right: f'{opening}{left}{before}{path}{args}{after}{right}{closing}',
        tildes,
        spaces,
        paths,
        arguments(values),
        spaces,
        tildes,
    )


texts = st.lists(st.sampled_from([c for c in ALPHABET if c != '{'] + ['{', ' ', '\n', '\r\n']), max_size=6).map(''.join)
comments = st.one_of(
    st.text(st.sampled_from(['a', ' ', '}', '-', '{']), max_size=4).map(lambda body: '{{!' + body + '}}'),
    st.text(st.sampled_from(['a', ' ', '}', '-']), max_size=4).map(lambda body: '{{!--' + body + '--}}'),
)
partials = st.builds(
    lambda before, target, args, after: f'{{{{>{before}{target}{args}{after}}}}}',
    spaces,
    st.one_of(
        paths, subexpressions, st.text(st.sampled_from(['a', 'b', '/']), max_size=3).map(lambda name: f'"{name}"')
    ),
    arguments(values),
    spaces,
)
raw_blocks = st.builds(
    lambda name, args, body, close: '{{{{' + name + args + '}}}}' + body + '{{{{/' + close + '}}}}',
    names,
    arguments(values),
    st.text(st.sampled_from(['a', '{', '}', '/', ' ']), max_size=6),
    names,
)


def blocks(bodies):
    def build(kind, space, name, args, body, alternative, close_name, same_name, newline, indent, tilde):
        alternative_text = ''
        if alternative is not None:
            marker, alternative_body = alternative
            alternative_text = f'{newline}{indent}{{{{{marker}}}}}{newline}{alternative_body}'
        close = name if same_name else close_name
        return (
            f'{indent}{{{{{tilde}{kind}{space}{name}{args}{tilde}}}}}{newline}{body}{alternative_text}'
            f'{newline}{indent}{{{{{tilde}/{close}}}}}{newline}'
        )

    return st.builds(
        build,
        st.sampled_from(['#', '^']),
        spaces,
        names,
        arguments(values),
        bodies,
        st.none() | st.tuples(st.sampled_from(['else', '^', ' else ', 'else ']), bodies),
        names,
        st.sampled_from([True, True, True, False]),
        st.one_of(st.just(''), line_ends),
        st.sampled_from(['', '', ' ', '\t ']),
        tildes,
    )


well_formed = st.recursive(
    st.one_of(
        texts,
        mustaches('{{', '}}'),
        mustaches('{{{', '}}}'),
        mustaches('{{&', '}}'),
        comments,
        partials,
        raw_blocks,
        st.sampled_from(['{{', '}}', '{{}}', '{{else}}', '{{^}}', '\r\n', '  \n', '{{~', '~}}', '{{~else~}}']),
    ),
    lambda inner: st.one_of(
        blocks(st.lists(inner, max_size=3).map(''.join)), st.lists(inner, min_size=2, max_size=4).map(''.join)
    ),
    max_leaves=12,
)


@st.composite
def edited(draw, base):
    """``base``, with up to three characters inserted, deleted or replaced."""
    source = draw(base)
    for _ in range(draw(st.integers(0, 3))):
        position = draw(st.integers(0, len(source)))
        operation = draw(st.sampled_from(['insert', 'delete', 'replace']))
        if operation == 'insert' or not source:
            source = source[:position] + draw(any_character) + source[position:]
        elif operation == 'delete':
            source = source[:position] + source[position + 1:]
        else:
            index = min(position, len(source) - 1)
            source = source[:index] + draw(any_character) + source[index + 1:]
    return source


templates = st.one_of(well_formed, edited(well_formed))
