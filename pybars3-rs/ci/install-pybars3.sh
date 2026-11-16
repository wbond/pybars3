#!/bin/sh
# Installs the pybars3 that pybars3-rs is tested against: the one of this
# repository, or a release (such as 0.9.6) from PyPI, whose test suite then
# comes from its tag, for tests/test_pybars_acceptance.py. Run it from the
# pybars3-rs directory.
set -eu
if [ "$1" = repository ]; then
    python -m pip install ..
else
    python -m pip install "pybars3==$1" PyMeta3==0.5.1
    echo "PYBARS_TESTS=$(sh ci/pybars3-tests.sh "$1")" >> "${GITHUB_ENV:-/dev/stdout}"
fi
