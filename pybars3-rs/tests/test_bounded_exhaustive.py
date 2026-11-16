"""Every short template over one character of each class pybars_rs and pybars tell apart.

``alphabet.py`` derives the classes from pybars' grammars and the CPython
predicates they use, so these templates stand for every template of the same
length. ``EXHAUSTIVE_MAX_LENGTH`` sets the length: 2 by default (4,033
templates), 3 in CI (254,080 templates), 4 in the weekly run (about 16
million, split over CI jobs with ``EXHAUSTIVE_PART`` of ``EXHAUSTIVE_PARTS``).
Within a run, the work is split into shards, each reported on its own.
"""

import itertools
import os
import unittest

import pybars._compiler

from tests import alphabet, parity

MAX_LENGTH = int(os.environ.get('EXHAUSTIVE_MAX_LENGTH', '2'))
PART = int(os.environ.get('EXHAUSTIVE_PART', '0'))
PARTS = int(os.environ.get('EXHAUSTIVE_PARTS', '1'))
SHARDS = 16


def template_count(max_length):
    return sum(len(alphabet.alphabet()) ** length for length in range(max_length + 1))


def template_at(index):
    """The template at ``index`` in the order of length, then of ``itertools.product``."""
    symbols = alphabet.alphabet()
    length, size = 0, 1
    while index >= size:
        index -= size
        length, size = length + 1, size * len(symbols)
    characters = []
    for _ in range(length):
        index, digit = divmod(index, len(symbols))
        characters.append(symbols[digit])
    return ''.join(reversed(characters))


def shard(max_length, number):
    """The templates of shard ``number`` of ``SHARDS`` in part ``PART`` of ``PARTS``."""
    step = PARTS * SHARDS
    return (template_at(index) for index in range(PART + number * PARTS, template_count(max_length), step))


class TestBoundedExhaustive(unittest.TestCase):

    def test_every_short_template_matches_pybars(self):
        for number in range(SHARDS):
            with self.subTest(shard=number):
                report = parity.check_all(shard(MAX_LENGTH, number))
                self.assertFalse(report.mismatches, report.failure_message())

    def test_the_shards_cover_every_template_once(self):
        symbols = alphabet.alphabet()
        expected = [''.join(c) for length in range(3) for c in itertools.product(symbols, repeat=length)]
        self.assertEqual([template_at(index) for index in range(template_count(2))], expected)
        covered = sorted(index for number in range(SHARDS) for index in range(number, template_count(2), SHARDS))
        self.assertEqual(covered, list(range(template_count(2))))

    def test_the_alphabet_covers_every_literal_and_class(self):
        symbols = set(alphabet.alphabet())
        literals = alphabet.grammar_literals(pybars._compiler.handlebars_grammar)
        literals |= set(alphabet.WHITESPACE_CONTROL_LITERALS)
        self.assertLessEqual({character for literal in literals for character in literal}, symbols)
        # The classes, plus the second plain letter.
        self.assertEqual(len(alphabet.character_classes()), len(symbols) - 1)
        # Look-alikes that pybars treats differently must not share a class.
        for ascii_character, other in [
            ('0', '\u00b2'),
            ('0', '\u0660'),
            ('A', '\u00bc'),
            (' ', '\x0b'),
            (' ', '\u0085'),
            ('a', '\u00e9'),
            ('\u00e9', '\u0100'),
            ('~', '-'),
        ]:
            self.assertNotEqual(alphabet.class_of(ascii_character), alphabet.class_of(other))
        self.assertNotEqual(alphabet.class_of('\ud800'), alphabet.class_of('\x00'))
        # From the compile grammar's "this".
        self.assertIn('h', symbols)
