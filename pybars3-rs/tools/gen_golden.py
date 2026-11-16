"""Generate the golden corpora of the Rust tests from pybars itself.

``compiler/tests/golden.rs`` checks, with ``cargo test`` alone, that the
crate gives pybars' result for every template of
``compiler/tests/golden/pybars-<version>.jsonl``: the generated module (as a
64-bit FNV-1a hash and a length), pybars' error message, or the fallback that
the crate must report where pybars raises ``ValueError``. The templates are the
parity seed corpus, every template that pybars' own test suite compiles,
nested templates and random ones.

Run it with CPython 3.12 (Unicode 15.0.0) and the pybars whose corpus to
write, from the pybars3-rs directory: the pybars of the repository for
0.9.7, and pybars3 0.9.6 with the test suite of its tag::

    python tools/gen_golden.py
    PYBARS_TESTS=path/to/0.9.6/tests python tools/gen_golden.py

With ``--check``, it fails instead if the file differs from what pybars gives,
which CI runs. The Python tests compare pybars_rs with pybars far more
extensively; these corpora let Rust contributors catch regressions without
Python.
"""

import argparse
import contextlib
import io
import json
import pathlib
import random
import sys
import unicodedata
import unittest
import warnings

warnings.simplefilter('ignore')

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pybars  # noqa: E402

from tests import corpus, parity, upstream  # noqa: E402

RANDOM_TEMPLATES = 800
#: The deepest nesting the crate compiles (Options::MAX_NESTING_LIMIT).
MAX_NESTING = 20


def output():
    return ROOT / 'compiler' / 'tests' / 'golden' / ('pybars-%s.jsonl' % pybars.__version__)


def fnv1a(text):
    value = 0xCBF29CE484222325
    for byte in text.encode('utf-8'):
        value = ((value ^ byte) * 0x100000001B3) % (1 << 64)
    return '%016x' % value


def upstream_templates():
    """Every template that pybars' own test suite compiles."""
    directory, problem = upstream.find()
    if directory is None:
        raise SystemExit(problem)
    acceptance, compiler_tests = upstream.load(directory)
    seen = []
    original = pybars.Compiler._generate_code

    def recording(self, source):
        if isinstance(source, str):
            seen.append(source)
        return original(self, source)

    pybars.Compiler._generate_code = recording
    try:
        suite = unittest.TestSuite()
        loader = unittest.defaultTestLoader
        for case in (acceptance.TestAcceptance, compiler_tests.TestCompiler):
            suite.addTests(loader.loadTestsFromTestCase(case))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    finally:
        pybars.Compiler._generate_code = original
    return seen


def entry(source):
    try:
        code = pybars.Compiler().precompile(source)
    except pybars.PybarsError as error:
        return {'source': source, 'error': str(error)}
    except ValueError:
        return {'source': source, 'fallback': 'int_conversion'}
    except RecursionError:
        return None
    return {'source': source, 'code_fnv1a': fnv1a(code), 'code_len': len(code.encode('utf-8'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='fail if the corpus of the installed pybars is stale')
    args = parser.parse_args()
    if unicodedata.unidata_version != '15.0.0':
        raise SystemExit('run with CPython 3.12 (Unicode 15.0.0)')
    rng = random.Random(20261104)
    candidates = (
        corpus.SEED_CORPUS
        + upstream_templates()
        + [corpus.nested_template(shape, depth) for shape in corpus.NESTED_SHAPES for depth in (1, 2, 5, 12, 18)]
        + [corpus.random_template(rng) for _ in range(RANDOM_TEMPLATES)]
    )
    entries, seen = [], set()
    for source in candidates:
        if source in seen:
            continue
        seen.add(source)
        # Rust strings cannot hold lone surrogates (pybars_rs runs pybars for them).
        if any(0xD800 <= ord(c) <= 0xDFFF for c in source):
            continue
        # Deeper templates fall back to pybars, which test_recursion.py covers.
        result = parity.pybars_rs._native.precompile(
            source, pybars_version=pybars.__version__, unicode_version='15.0.0', nesting_limit=MAX_NESTING)
        if result == ('fallback', 'nesting_depth'):
            continue
        item = entry(source)
        if item is not None:
            entries.append(item)
    text = ''.join(json.dumps(item, ensure_ascii=True) + '\n' for item in entries)
    kinds = {kind: sum(kind in item for item in entries) for kind in ('code_fnv1a', 'error', 'fallback')}
    path = output()
    name = path.relative_to(ROOT)
    if args.check:
        if not path.exists() or path.read_text(encoding='utf-8') != text:
            sys.stderr.write('%s differs from pybars: run tools/gen_golden.py\n' % name)
            return 1
        print('%s matches pybars on %d templates: %s' % (name, len(entries), kinds))
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    print('wrote %d templates to %s: %s' % (len(entries), name, kinds))
    return 0


if __name__ == '__main__':
    sys.exit(main())
