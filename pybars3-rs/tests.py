import unittest

from tests.test_api import TestApi                                    # noqa: F401
from tests.test_benchmark import TestBenchmark                        # noqa: F401
from tests.test_bounded_exhaustive import TestBoundedExhaustive       # noqa: F401
from tests.test_differential_fuzz import TestDifferentialFuzz         # noqa: F401
from tests.test_harness import TestHarness                            # noqa: F401
from tests.test_properties import TestProperties                      # noqa: F401
from tests.test_pybars_acceptance import TestUpstreamAcceptance       # noqa: F401
from tests.test_pybars_acceptance import TestUpstreamCompiler         # noqa: F401
from tests.test_pybars_acceptance import TestUpstreamSuite            # noqa: F401
from tests.test_recursion import TestRecursion                        # noqa: F401
from tests.test_seed_corpus import TestSeedCorpus                     # noqa: F401
from tests.test_stress import TestStress                              # noqa: F401


if __name__ == '__main__':
    unittest.main()
