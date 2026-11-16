#!/bin/sh
# Extracts the test suite of a pybars3 release (such as 0.9.6) from its tag,
# and prints the directory that holds it. Forks of the repository may not
# have the tags, which then come from wbond/pybars3.
set -eu
top="$(git rev-parse --show-toplevel)"
if ! git -C "$top" rev-parse -q --verify "refs/tags/$1" >/dev/null; then
    git -C "$top" fetch -q --depth=1 https://github.com/wbond/pybars3.git "refs/tags/$1:refs/tags/$1"
fi
directory="${RUNNER_TEMP:-/tmp}/pybars3-$1"
mkdir -p "$directory"
git -C "$top" archive "$1" tests | tar -x -C "$directory"
echo "$directory/tests"
