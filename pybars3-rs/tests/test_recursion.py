"""RecursionError parity: pybars_rs raises it exactly when pybars does.

pybars parses with Python recursion, so whether a template compiles depends on
how deep the caller's stack already is and on ``sys.getrecursionlimit()``.
pybars_rs takes the fast path only when pybars would fit in the stack headroom
left (with the bound in ``native/src/recursion.rs``), and otherwise runs
pybars itself without adding a frame. Both are checked at every recursion
limit around each template's boundary.
"""

import os
import random
import subprocess
import sys
import threading
import unittest

import pybars
import pybars_rs

from tests import corpus, parity
from tests.parity import Outcome, safe_repr

SHAPES = list(corpus.NESTED_SHAPES)

TESTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fast_path_boundary(source, low, high):
    """The lowest recursion limit at which pybars_rs takes the fast path for ``source`` from here."""
    while low < high:
        middle = (low + high) // 2
        before = pybars_rs.counters()['fast_path']
        parity.outcomes_at_limit(source, middle)
        if pybars_rs.counters()['fast_path'] == before:
            low = middle + 1
        else:
            high = middle
    return low


def compare_at_limits(source):
    """Compare pybars_rs with pybars around pybars' RecursionError boundary
    and around the limit from which pybars_rs takes the fast path.

    :return:
        A tuple of (both boundaries, the mismatches)
    """
    floor = parity.stack_depth() + 20
    boundary = parity.recursion_boundary(source, floor, 20000)
    switch = fast_path_boundary(source, floor, 20000)
    mismatches = []
    # The safety property: where pybars_rs compiles on its own, pybars compiles.
    if switch < boundary:
        mismatches.append((safe_repr(source), 'fast path below the boundary', boundary, switch))
    limits = set(range(max(floor, boundary - 5), boundary + 6)) | set(range(max(floor, switch - 5), switch + 6))
    for limit in sorted(limits):
        expected, actual = parity.outcomes_at_limit(source, limit)
        if expected != actual:
            mismatches.append((safe_repr(source), limit, boundary, switch, expected.describe(), actual.describe()))
    return (boundary, switch), mismatches


def run_in_a_fresh_interpreter(script):
    """Run ``script`` where pybars_rs has not compiled anything yet."""
    environment = dict(os.environ, PYTHONWARNINGS='ignore')
    subprocess.run([sys.executable, '-c', script, TESTS_ROOT], check=True, env=environment)


#: Compares pybars and pybars_rs at limits around pybars' recursion boundary
#: for ``source``, from the top of a fresh interpreter, pybars_rs last.
BOUNDARY_SCRIPT = """
import sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
import pybars, pybars_rs
from tests import corpus, parity

source = {source}

def at_limit(compiler, limit):
    previous = sys.getrecursionlimit()
    sys.setrecursionlimit(limit)
    try:
        return parity.Outcome.capture(lambda: compiler().precompile(source))
    finally:
        sys.setrecursionlimit(previous)

low, high = parity.stack_depth() + 5, 20000
while low < high:
    middle = (low + high) // 2
    if at_limit(pybars.Compiler, middle).error_class is RecursionError:
        low = middle + 1
    else:
        high = middle
# pybars_rs' first compile in this interpreter, at pybars' boundary.
expected, actual = at_limit(pybars.Compiler, low), at_limit(pybars_rs.Compiler, low)
assert pybars_rs.counters()[{reason!r}] == 1, pybars_rs.counters()
assert expected == actual and actual.source is not None, (low, expected.describe(), actual.describe())
expected, actual = at_limit(pybars.Compiler, low - 1), at_limit(pybars_rs.Compiler, low - 1)
assert expected == actual and actual.error_class is RecursionError, (low, expected.describe(), actual.describe())
"""


class TestRecursion(unittest.TestCase):

    def test_recursion_errors_match_at_both_boundaries(self):
        for shape in SHAPES:
            for depth in (1, 8, 18):
                # Slow under pybars, and covered by the other shapes.
                if shape == 'mixed' and depth > 8:
                    continue
                with self.subTest(shape=shape, depth=depth):
                    (boundary, switch), mismatches = compare_at_limits(corpus.nested_template(shape, depth))
                    self.assertFalse(mismatches)
                    # Nor is the bound needlessly conservative.
                    self.assertLess(switch - boundary, 200, (shape, depth, boundary, switch))

    def test_templates_deeper_than_the_port_compiles_fall_back(self):
        for shape in ('blocks', 'else blocks', 'subexpressions', 'unclosed blocks'):
            for depth in (19, 20, 21, 40, 60, 75, 200):
                with self.subTest(shape=shape, depth=depth):
                    source = corpus.nested_template(shape, depth)
                    expected = Outcome.capture(lambda: pybars.Compiler().precompile(source))
                    actual = Outcome.capture(lambda: pybars_rs.Compiler().precompile(source))
                    self.assertEqual(expected, actual, (expected.describe(), actual.describe()))

    def test_shallow_templates_take_the_fast_path_at_the_default_limit(self):
        self.assertEqual(sys.getrecursionlimit(), 1000)
        for shape in SHAPES:
            source = corpus.nested_template(shape, 12)
            result = pybars_rs._GENERATE_CODE.try_fast_path(source)
            self.assertNotIsInstance(result, str, (shape, result, safe_repr(source)))

    def test_random_templates_match_at_both_boundaries(self):
        for seed in range(3):
            rng = random.Random(seed)
            for _ in range(15):
                outer = rng.choice(['{}', '{{{{#if a}}}}{}{{{{/if}}}}', '{{{{foo (bar {})}}}}'])
                source = outer.format(corpus.random_template(rng))
                with self.subTest(seed=seed, source=safe_repr(source)):
                    self.assertFalse(compare_at_limits(source)[1])

    def test_deep_templates_on_a_small_thread_stack_match_pybars(self):
        """The port bounds its native stack: deep templates fall back, they do not crash."""
        mismatches = []
        previous = threading.stack_size()

        def work():
            for shape in ['blocks', 'else blocks', 'subexpressions', 'partial name', 'unclosed blocks']:
                for depth in (5, 10, 19, 20, 65):
                    source = corpus.nested_template(shape, depth)
                    expected = Outcome.capture(lambda: pybars.Compiler().precompile(source))
                    actual = Outcome.capture(lambda: pybars_rs.Compiler().precompile(source))
                    if expected != actual:
                        mismatches.append((shape, depth, expected.describe(), actual.describe()))

        # On CPython 3.10 every Python call also recurses in C, and pybars
        # itself needs more than 1 MiB at these depths.
        threading.stack_size((256 if sys.version_info >= (3, 11) else 4096) * 1024)
        try:
            thread = threading.Thread(target=work)
            thread.start()
            thread.join()
        finally:
            threading.stack_size(previous)
        self.assertFalse(mismatches)

    def test_the_nesting_limit_follows_the_stack_headroom(self):
        self.assertEqual(pybars_rs._GENERATE_CODE.nesting_limit(), 20)
        floor = parity.stack_depth()
        with parity.recursion_limit(floor + 200):
            lowered = pybars_rs._GENERATE_CODE.nesting_limit()
        with parity.recursion_limit(floor + 45):
            self.assertEqual(pybars_rs._GENERATE_CODE.nesting_limit(), 0)
        self.assertTrue(0 < lowered < 20, lowered)

    def test_the_first_fallback_matches_pybars_at_its_recursion_boundary(self):
        script = BOUNDARY_SCRIPT.format(source='corpus.nested_template("blocks", 25)', reason='nesting_depth')
        run_in_a_fresh_interpreter(script)

    def test_a_low_recursion_limit_does_not_break_the_first_fallback(self):
        # A shallow template at a limit far below the default: the fallback
        # must need nothing that pybars, whose grammars were built at import,
        # does not.
        script = BOUNDARY_SCRIPT.format(source='"a\\ud800b {{x}}"', reason='surrogates')
        run_in_a_fresh_interpreter(script)
