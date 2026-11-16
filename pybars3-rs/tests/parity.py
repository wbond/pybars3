"""Compare pybars_rs with the installed pybars, the oracle.

Every input is compared two ways:

* the Rust compiler alone (``fast_path``) with pybars' ``precompile()``: the
  same generated source or the same ``PybarsError``, unless it falls back for
  a reason that pybars' result confirms (pybars raises ``ValueError`` for an
  integer literal, for example);
* ``pybars_rs.Compiler().precompile()``, fallbacks included, with
  ``pybars.Compiler().precompile()``: the same source, or the same exception
  class and message.

The inputs are in ``corpus.py``, the mutants that the harness must notice in
``mutants.py``. ``python -m tests.parity`` runs long fuzz campaigns, or checks
a directory of real templates and prints only hashes and metadata about them.
"""

import argparse
import collections
import contextlib
import dataclasses
import gc
import hashlib
import itertools
import pathlib
import random
import sys

import pybars
import pybars_rs

from tests import corpus

GENERATE_CODE = pybars_rs._GENERATE_CODE


@dataclasses.dataclass(frozen=True)
class Outcome:

    """The comparable result of compiling one template."""

    source: object
    error_class: object = None
    error_message: object = None

    @classmethod
    def capture(cls, call):
        try:
            return cls(source=call())
        except BaseException as error:  # RecursionError and friends are outcomes too
            return cls(source=None, error_class=type(error), error_message=str(error))

    def describe(self):
        if self.source is not None:
            return 'source(%d chars)' % len(self.source)
        name = self.error_class.__name__ if self.error_class is not None else 'None'
        return '%s: %s' % (name, self.error_message)

    def summary(self):
        """Metadata only, safe to log for private templates."""
        if self.source is not None:
            return 'source(%d chars)' % len(self.source)
        return self.error_class.__name__ if self.error_class is not None else 'None'


def safe_repr(value, limit=160):
    """``repr`` that survives lone surrogates when printed."""
    text = repr(value)
    if len(text) > limit:
        text = text[:limit] + '...'
    return text.encode('utf-8', 'backslashreplace').decode('utf-8')


def first_difference(left, right):
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return None if len(left) == len(right) else min(len(left), len(right))


def difference(expected, actual):
    """How ``actual`` differs from pybars' ``expected``, or None."""
    if expected == actual:
        return None
    if expected.source is not None and actual.source is not None:
        offset = first_difference(expected.source, actual.source)
        return 'source differs at %d: pybars %s, pybars_rs %s' % (
            offset,
            safe_repr(expected.source[offset:offset + 50]),
            safe_repr(actual.source[offset:offset + 50]),
        )
    return 'pybars %s, pybars_rs %s' % (expected.describe(), actual.describe())


def pybars_outcome(source):
    # Looked up per call, so that a mutant can replace pybars.Compiler.
    return Outcome.capture(lambda: pybars.Compiler().precompile(source))


def pybars_rs_outcome(source):
    return Outcome.capture(lambda: pybars_rs.Compiler().precompile(source))


def fast_path(source):
    """The Rust compiler alone: ``(outcome, None)``, or ``(None, fallback reason)``."""
    try:
        result = GENERATE_CODE.try_fast_path(source)
    except BaseException as error:  # PybarsError is an outcome
        return Outcome(None, type(error), str(error)), None
    if isinstance(result, str):
        return None, result
    return Outcome(result.full_code), None


#: Fallback reasons that only happen where pybars raises, and what it raises.
FALLBACK_EXCEPTIONS = {
    'int_conversion': ValueError,
}


@dataclasses.dataclass
class Report:

    """What a batch of comparisons found."""

    inputs: int = 0
    fast_path: int = 0
    fallbacks: collections.Counter = dataclasses.field(default_factory=collections.Counter)
    mismatches: list = dataclasses.field(default_factory=list)

    def merge(self, other):
        self.inputs += other.inputs
        self.fast_path += other.fast_path
        self.fallbacks.update(other.fallbacks)
        self.mismatches.extend(other.mismatches)

    def failure_message(self, limit=20):
        lines = ['%d of %d inputs differ from pybars:' % (len(self.mismatches), self.inputs)]
        lines.extend('  %s: %s' % (safe_repr(source), problem) for source, problem in self.mismatches[:limit])
        return '\n'.join(lines)


def check(source, report):
    """Compare one template both ways, recording disagreements in ``report``."""
    report.inputs += 1
    expected = pybars_outcome(source)
    outcome, reason = fast_path(source)
    if reason is None:
        report.fast_path += 1
        problem = difference(expected, outcome)
        if problem is not None:
            report.mismatches.append((source, 'fast path: ' + problem))
    else:
        report.fallbacks[reason] += 1
        raised = FALLBACK_EXCEPTIONS.get(reason)
        if raised is not None and expected.error_class is not raised:
            report.mismatches.append((source, 'fell back (%s), but pybars gave %s' % (reason, expected.describe())))
    problem = difference(expected, pybars_rs_outcome(source))
    if problem is not None:
        report.mismatches.append((source, 'Compiler: ' + problem))


def check_all(sources):
    report = Report()
    for source in sources:
        check(source, report)
    return report


def fuzz_report(iterations, seed):
    """Compare ``iterations`` random templates from ``seed``."""
    rng = random.Random(seed)
    return check_all(corpus.random_template(rng) for _ in range(iterations))


def stack_depth():
    """The number of Python frames on the stack, this function's included."""
    depth, frame = 0, sys._getframe()
    while frame is not None:
        depth, frame = depth + 1, frame.f_back
    return depth


@contextlib.contextmanager
def recursion_limit(limit):
    """Run with ``limit`` as the recursion limit, and without the garbage
    collector, whose callbacks (Hypothesis has one) would run Python code at
    any depth."""
    previous = sys.getrecursionlimit()
    collecting = gc.isenabled()
    gc.disable()
    sys.setrecursionlimit(limit)
    try:
        yield
    finally:
        sys.setrecursionlimit(previous)
        if collecting:
            gc.enable()


def outcomes_at_limit(source, limit):
    """pybars and pybars_rs, each called from the same stack depth with ``limit``."""
    with recursion_limit(limit):
        expected = Outcome.capture(lambda: pybars.Compiler().precompile(source))
        actual = Outcome.capture(lambda: pybars_rs.Compiler().precompile(source))
    return expected, actual


def pybars_outcome_at_limit(source, limit):
    """pybars alone, as ``outcomes_at_limit`` calls it (at the same stack depth)."""
    with recursion_limit(limit):
        return Outcome.capture(lambda: pybars.Compiler().precompile(source))


def recursion_boundary(source, low, high):
    """The lowest recursion limit at which pybars compiles ``source`` from here."""
    while low < high:
        middle = (low + high) // 2
        if pybars_outcome_at_limit(source, middle).error_class is RecursionError:
            low = middle + 1
        else:
            high = middle
    return low


# ----------------------------------------------------------------------
# pybars' own test suite (test_pybars_acceptance.py)
# ----------------------------------------------------------------------


class OracleMismatch(BaseException):

    """pybars_rs and pybars disagreed.

    Not an ``Exception``, so that ``assertRaises(Exception)`` in a test cannot
    swallow it.
    """


@contextlib.contextmanager
def checked_compiler(*modules):
    """Make ``Compiler`` in pybars and in ``modules`` a ``pybars_rs.Compiler`` that checks itself against pybars.

    ``compile()``, ``precompile()`` and ``template()`` all go through
    ``_generate_code``, so pybars' tests exercise pybars_rs while pybars
    renders. Every call is also run through pybars, and any difference raises
    ``OracleMismatch``. Yields the counts of what the compiles did.
    """
    original = pybars.Compiler
    counts = collections.Counter()

    def pybars_compiler():
        compiler = original()
        # A private code builder: pybars' own is shared by the class.
        compiler._compiler = pybars_rs._new_compile_grammar()
        return compiler

    class CheckedCompiler(pybars_rs.Compiler):
        def _generate_code(self, source):
            counts['calls'] += 1
            expected = Outcome.capture(lambda: original._generate_code(pybars_compiler(), source).full_code)
            outcome, reason = fast_path(source)
            counts['fast_path' if reason is None else reason] += 1
            if outcome is not None:
                problem = difference(expected, outcome)
                if problem is not None:
                    raise OracleMismatch('%s: fast path: %s' % (safe_repr(source), problem))
            actual = Outcome.capture(lambda: pybars_rs.Compiler._generate_code(self, source).full_code)
            problem = difference(expected, actual)
            if problem is not None:
                raise OracleMismatch('%s: %s' % (safe_repr(source), problem))
            return pybars_rs.Compiler._generate_code(self, source)

    patched = [pybars] + list(modules)
    for module in patched:
        module.Compiler = CheckedCompiler
    try:
        yield counts
    finally:
        for module in patched:
            module.Compiler = original


# ----------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------


def check_directory(directory):
    """Compare every file under ``directory``, printing only hashes and metadata."""
    report = Report()
    files = sorted(path for path in pathlib.Path(directory).rglob('*') if path.is_file())
    for path in files:
        source = path.read_text(encoding='utf-8', errors='surrogateescape')
        before = len(report.mismatches)
        check(source, report)
        for _, problem in report.mismatches[before:]:
            digest = hashlib.sha256(source.encode('utf-8', 'surrogatepass')).hexdigest()[:16]
            kind = problem.split(':')[0]
            print('MISMATCH sha256=%s length=%d kind=%s' % (digest, len(source), kind))
    print('%d templates: fast path %d, fallbacks %s, %d mismatches' % (
        len(files), report.fast_path, dict(report.fallbacks), len(report.mismatches)))
    return 1 if report.mismatches or not files else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fuzz', type=int, default=0, metavar='N', help='compare N random templates')
    parser.add_argument('--seed', type=int, default=0, help='the first random seed')
    parser.add_argument('--corpus', metavar='DIR', help='compare every file in DIR (prints hashes only)')
    args = parser.parse_args(argv)
    if args.corpus:
        return check_directory(args.corpus)
    report = check_all(corpus.SEED_CORPUS)
    for seed in itertools.count(args.seed):
        if report.inputs >= args.fuzz + len(corpus.SEED_CORPUS):
            break
        report.merge(fuzz_report(min(10000, args.fuzz + len(corpus.SEED_CORPUS) - report.inputs), seed))
    print('%d inputs: fast path %d, fallbacks %s' % (report.inputs, report.fast_path, dict(report.fallbacks)))
    if report.mismatches:
        print(report.failure_message())
        return 1
    print('no mismatches')
    return 0


if __name__ == '__main__':
    sys.exit(main())
