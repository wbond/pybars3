import sys
import unittest

from tests.test__compiler import TestCompiler      # noqa: F401
from tests.test_acceptance import TestAcceptance   # noqa: F401

if len(sys.argv) >= 2 and sys.argv[1] == '--debug':
    import pybars
    pybars._compiler.debug = True
    del sys.argv[1]


if __name__ == '__main__':
    unittest.main()
