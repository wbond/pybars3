"""Measure how many Python frames pybars needs per level of template nesting.

pybars_rs falls back to pybars when a template's nesting could take pybars
past ``sys.getrecursionlimit()`` from the current stack depth, using the bound
``BASE_FRAMES + FRAMES_PER_LEVEL * depth`` (see ``native/src/recursion.rs``).
This prints, for this interpreter and the installed pybars, the frames pybars
needs for nested templates of several shapes and the smallest constants that
bound them all. Run it from the pybars3-rs directory with every supported
CPython, and with pybars3 0.9.6 as well as the pybars of the repository::

    for v in 3.10 3.11 3.12 3.13 3.14 3.15; do
        uv run --no-project --python $v --with .. --with . python tools/calibrate_recursion.py
        uv run --no-project --python $v --with pybars3==0.9.6 --with . python tools/calibrate_recursion.py
    done

``tests/test_recursion.py`` checks the bound that the binding uses.
"""

import random
import sys
import warnings

warnings.simplefilter('ignore', SyntaxWarning)

import pybars  # noqa: E402

from pybars_rs import _native  # noqa: E402

SHAPES = {
    'blocks': lambda n: '{{#if a}}' * n + 'x' + '{{/if}}' * n,
    'else blocks': lambda n: '{{#if a}}x{{else}}' * n + 'y' + '{{/if}}' * n,
    'inverted blocks': lambda n: '{{^if a}}' * n + 'x' + '{{/if}}' * n,
    'standalone blocks': lambda n: '{{#if a}}\n' * n + 'x\n' + '{{/if}}\n' * n,
    'subexpressions': lambda n: '{{foo ' + '(bar ' * n + 'a' + ')' * n + '}}',
    'keyword subexpressions': lambda n: '{{foo ' + '(bar kk=' * n + 'a' + ')' * n + '}}',
    'partial name': lambda n: '{{> ' + '(bar ' * n + 'a' + ')' * n + '}}',
    'unclosed blocks': lambda n: '{{#if a}}' * n + 'x',
    'mixed': lambda n: '{{#each xs}}{{foo (bar (baz a))}}' * n + '{{/each}}' * n,
    'block in subexpression arguments': lambda n: '{{#if (a (b c))}}' * n + 'x' + '{{/if}}' * n,
}


def stack_depth():
    depth, frame = 0, sys._getframe()
    while frame is not None:
        depth, frame = depth + 1, frame.f_back
    return depth


def compiles_at(source, limit):
    previous = sys.getrecursionlimit()
    sys.setrecursionlimit(limit)
    try:
        pybars.Compiler().precompile(source)
    except RecursionError:
        return False
    except Exception:  # noqa: BLE001 - other errors are not about the stack
        return True
    finally:
        sys.setrecursionlimit(previous)
    return True


def frames_needed(source):
    """The frames above this function's caller that pybars needs for ``source``."""
    low, high = 10, 5000
    while low < high:
        middle = (low + high) // 2
        if compiles_at(source, middle):
            high = middle
        else:
            low = middle + 1
    # `compiles_at` runs one frame deeper than its caller.
    return low - (stack_depth() + 1)


def port_depth(source):
    """The nesting depth that pybars_rs counts for ``source``, or None if deeper than it compiles."""
    for limit in range(_native.MAX_NESTING_LIMIT + 1):
        result = _native.precompile(
            source, pybars_version=pybars.__version__, unicode_version='15.0.0', nesting_limit=limit
        )
        if result != ('fallback', 'nesting_depth'):
            return limit
    return None


def random_template(rng, depth):
    if depth == 0:
        return rng.choice(['x', '{{a}}', '{{a b}}', '{{foo (bar)}}', '\n', ' '])
    inner = ''.join(random_template(rng, rng.randrange(depth)) for _ in range(rng.randint(1, 3)))
    return rng.choice(
        [
            lambda: '{{#if a}}' + inner + '{{/if}}',
            lambda: '{{^x}}' + inner + '{{else}}' + inner + '{{/x}}',
            lambda: '{{foo ' + '(bar ' * depth + 'a' + ')' * depth + '}}' + inner,
            lambda: '{{#each (a (b c))}}' + inner + '{{/each}}',
        ]
    )()


def main():
    samples = []
    for shape, build in SHAPES.items():
        for n in range(25):
            source = build(n)
            depth = port_depth(source)
            if depth is None:
                break
            samples.append((shape, depth, frames_needed(source)))
    rng = random.Random(0)
    for _ in range(150):
        source = random_template(rng, rng.randint(1, 6))
        depth = port_depth(source)
        if depth is not None:
            samples.append(('random', depth, frames_needed(source)))
    print(f'CPython {sys.version.split()[0]}, pybars {pybars.__version__}: {len(samples)} templates')
    for shape in [*SHAPES, 'random']:
        rows = sorted({(d, f) for s, d, f in samples if s == shape})
        print(f'  {shape:>32}: ' + ' '.join(f'{d}:{f}' for d, f in rows[:12]))
    deepest = _native.MAX_NESTING_LIMIT
    for per in range(14, 25):
        base = max(f - per * d for _, d, f in samples)
        reserved = base + per * deepest
        print(f'  FRAMES_PER_LEVEL={per}: BASE_FRAMES >= {base} (reserves {reserved} frames at depth {deepest})')


if __name__ == '__main__':
    main()
