"""pybars_rs must stay much faster than pybars, and this prints by how much.

The floor is loose because CI machines are noisy; ``BENCHMARK=1`` prints the
table. "precompile" is ``Compiler().precompile()``; "validate" adds CPython's
``compile()`` of the generated module, which is the same for both and
dominates pybars_rs' time on large templates.
"""

import os
import sys
import time
import unittest

import pybars
import pybars_rs

from tests import corpus

FLOOR = 20.0

#: The shortest measurement: Windows' thread clock ticks every 15.6 ms.
MIN_SECONDS = 0.1


def best_cpu_ms(call, repeat, runs=3):
    """Best of ``runs`` runs of the mean thread CPU time per call, in milliseconds.

    Each run makes at least ``repeat`` calls, and more until it lasts
    ``MIN_SECONDS``.
    """
    best = float('inf')
    for _ in range(runs):
        calls = 0
        started = time.thread_time()
        while calls < repeat or time.thread_time() - started < MIN_SECONDS:
            call()
            calls += 1
        best = min(best, (time.thread_time() - started) / calls * 1000.0)
    return best


def validate(compiler, source):
    return lambda: compile(compiler().precompile(source), '<template>', 'exec', dont_inherit=True)


class TestBenchmark(unittest.TestCase):

    def test_pybars_rs_is_much_faster_than_pybars(self):
        for label, source in corpus.BENCH_SIZES.items():
            with self.subTest(label=label):
                repeat = max(1, min(20, 20000 // len(source)))
                pybars_ms = best_cpu_ms(lambda: pybars.Compiler().precompile(source), repeat)
                native_ms = best_cpu_ms(lambda: pybars_rs.Compiler().precompile(source), repeat * 20)
                if os.environ.get('BENCHMARK'):
                    pybars_validate = best_cpu_ms(validate(pybars.Compiler, source), repeat)
                    native_validate = best_cpu_ms(validate(pybars_rs.Compiler, source), repeat * 4)
                    sys.stderr.write('\n%7s: precompile %9.3f ms -> %7.3f ms (%6.1fx); validate %9.3f ms -> %7.3f ms (%5.1fx)' % (
                        label, pybars_ms, native_ms, pybars_ms / native_ms,
                        pybars_validate, native_validate, pybars_validate / native_validate))
                self.assertGreater(pybars_ms / native_ms, FLOOR)
