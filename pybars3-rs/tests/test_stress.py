"""Resource behaviour, with bounds loose enough for shared CI machines.

* the port is linear on adversarial inputs (time per character must not grow
  with the input), including the whitespace runs on which pybars3 0.9.7's
  regular expressions are quadratic;
* compiles leave no modules behind and do not grow memory;
* the GIL is released while the port compiles, and threads get identical
  results.
"""

import concurrent.futures
import sys
import threading
import time
import tracemalloc
import unicodedata
import unittest

import pybars
import pybars_rs
from pybars_rs import _native

from tests import corpus

#: The shortest measurement: Windows' thread clock ticks every 15.6 ms.
MIN_SECONDS = 0.1


def microseconds_per_character(source):
    """The thread CPU time of the port per character, over calls lasting ``MIN_SECONDS``."""
    calls = 0
    started = time.thread_time()
    while calls == 0 or time.thread_time() - started < MIN_SECONDS:
        _native.precompile(source, pybars_version=pybars.__version__, unicode_version=unicodedata.unidata_version)
        calls += 1
    return (time.thread_time() - started) / calls / max(len(source), 1) * 1e6


class TestStress(unittest.TestCase):

    def test_the_port_is_linear_on_adversarial_inputs(self):
        for name, build in corpus.ADVERSARIAL.items():
            with self.subTest(name=name):
                small = min(microseconds_per_character(build(4000)) for _ in range(3))
                large = min(microseconds_per_character(build(160000)) for _ in range(3))
                # Linear is ~1x; quadratic would be ~40x.
                self.assertLess(large, max(small, 0.05) * 5, (name, small, large))

    def test_compiles_leak_neither_modules_nor_memory(self):
        for index in range(1000):
            pybars_rs.precompile('hello {{name_%d}}' % index)
        modules = len(sys.modules)
        tracemalloc.start()
        try:
            before, _ = tracemalloc.get_traced_memory()
            for index in range(20000):
                pybars_rs.precompile('hello {{name_%d}} %d' % (index % 1000, index))
            after, _ = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(sys.modules), modules)
        self.assertLess(after - before, 1024 * 1024)

    def test_threads_get_identical_results(self):
        template = corpus.MESSAGE_TEMPLATE * 5
        expected = pybars_rs.precompile(template)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(pybars_rs.precompile, [template] * 400))
        self.assertTrue(all(result == expected for result in results))

    def test_the_gil_is_released_while_compiling(self):
        template = 'x' * 20000000
        progress = [0]
        stop = threading.Event()

        def spin():
            while not stop.is_set():
                progress[0] += 1

        spinner = threading.Thread(target=spin)
        spinner.start()
        try:
            time.sleep(0.05)
            before = progress[0]
            started = time.perf_counter()
            pybars_rs.precompile(template)
            elapsed = time.perf_counter() - started
            during = progress[0] - before
        finally:
            stop.set()
            spinner.join()
        # With the GIL held for the whole compile, the spinner could only run
        # in the switch intervals (5 ms) before and after it.
        self.assertGreater(elapsed, 0.02)
        self.assertGreater(during, 0, elapsed)
