"""Random templates, each compared with pybars.

The templates join pieces of real templates and syntax errors, then insert,
delete or replace a few characters taken from those that pybars' grammar, the
CPython predicates it uses and ``repr()`` tell apart. ``FUZZ_ITERATIONS``
changes the number per seed; ``python -m tests.parity --fuzz N`` runs longer
campaigns.
"""

import os
import unittest

from tests import parity

ITERATIONS = int(os.environ.get('FUZZ_ITERATIONS', '2500'))


class TestDifferentialFuzz(unittest.TestCase):

    def test_random_templates_match_pybars(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                report = parity.fuzz_report(ITERATIONS, seed)
                self.assertFalse(report.mismatches, report.failure_message())
                # Most templates take the fast path; the comparison is about the port.
                self.assertGreater(report.fast_path, ITERATIONS * 0.9, report)
