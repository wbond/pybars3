# pybars3-rs - pybars3's template compiler in Rust

`pybars_rs.Compiler` is a drop-in replacement for `pybars.Compiler` that
generates the same Python source, byte for byte, 500 to 750 times faster (see
[Performance](#performance)), without holding the GIL, and safely from many
threads at once. It reproduces pybars3 0.9.6 and 0.9.7 (the master branch has
0.9.7's compiler).

```python
import pybars_rs

render = pybars_rs.Compiler().compile(u"Hello {{name}}!")
render({'name': 'world'})  # u'Hello world!'

source = pybars_rs.precompile(u"Hello {{name}}!")
# The Python module that pybars.Compiler().precompile() returns, byte for byte.
```

This directory has two parts:

| | What | Built as |
| --- | --- | --- |
| [`compiler/`](compiler) | The compiler, in plain Rust: no dependencies, no `unsafe` | the `pybars3-compiler` crate |
| [`native/`](native), [`pybars_rs/`](pybars_rs) | The Python package: the PyO3 extension module and the drop-in `Compiler` | the `pybars3-rs` wheel |

## Why

pybars compiles a template to Python source and runs it. The compiler half is
the slow part: pybars parses with [PyMeta], a PEG interpreter written in pure
Python, at about 20 µs per character, and it keeps its code builder on the
`Compiler` class, so concurrent compiles corrupt each other and callers have to
serialize them. Applications that compile many templates, or compile them on a
request path to validate them, spend most of that time in the parser.

pybars3-rs reimplements that compiler, and only that: the generated code still
runs on pybars' own runtime (helpers, scopes, escaping), so rendering behaves
exactly as before, and code that caches generated source keeps working.

## Installation

```bash
pip install pybars3-rs
```

It installs pybars3 (0.9.6 or 0.9.7) and PyMeta3 0.5.1 if they are missing.
There are wheels for CPython 3.10 and later (one `abi3` wheel per platform)
and for free-threaded CPython 3.14, on Linux, macOS and Windows. Building from
source needs a Rust toolchain, 1.85 or newer.

## Usage

`pybars_rs.Compiler` subclasses `pybars.Compiler` and replaces one method,
`_generate_code`, which `compile()`, `precompile()` and `template()` use to
turn template text into Python. Everything else is pybars' own code.
`pybars_rs` also re-exports pybars' runtime names, so this works:

```python
import pybars_rs as pybars

compiler = pybars.Compiler()
template = compiler.compile(u"{{#each items}}<li>{{this}}</li>{{/each}}")
template({'items': ['a', 'b']})  # u'<li>a</li><li>b</li>'

try:
    compiler.compile(u"{{#if a}}{{/each}}")
except pybars.PybarsError as error:  # pybars' own exception, with pybars' message
    print(error)  # Error at character 16 of line 1 near {{/each}}
```

A few templates need CPython itself to get pybars' exact result: an integer
literal that `int()` rejects (pybars raises `ValueError`), nesting deep enough
to reach `sys.getrecursionlimit()` from the current stack, strings with lone
surrogates, `str` subclasses, and `pybars._compiler.debug`. For those,
pybars3-rs runs pybars' own `_generate_code`, from native code so that it runs
at the same stack depth and raises exactly what pybars raises.
`pybars_rs.counters()` reports how often each case happens:

```python
pybars_rs.counters()
# {'fast_path': 1520, 'unavailable': 0, 'debug': 0, 'not_str': 0,
#  'surrogates': 0, 'int_conversion': 1, 'nesting_depth': 0,
#  'panic': 0, 'internal': 0}
```

`panic` and `internal` count calls on which the Rust compiler failed in a way
it should not (a bug in pybars3-rs): those calls ran pybars too, so the result
is still pybars', but please report them.

pybars3-rs uses the Rust compiler only where it was verified: CPython with one
of the Unicode databases it has tables for, a `pybars/_compiler.py` that it was
verified against (pybars3 0.9.6, 0.9.7 or the master branch, checked by
SHA-256 at import), PyMeta3 0.5.1, and a self-check at import. Anywhere else,
or with `PYBARS_RS_DISABLE=1` in the environment, `pybars_rs.Compiler` behaves
exactly like `pybars.Compiler`, and `pybars_rs.unavailable_reason()` says why.
Export `pybars_rs.is_available()` as a metric if you depend on the speed.

The Rust crate can be used without Python, see
[its readme](compiler/readme.md).

## Compatibility

* **pybars3 0.9.6 and 0.9.7.** The generated source is pybars' byte for byte,
  including its header (which checks `pybars.__version__` at run time), and
  syntax errors have pybars' messages. The two releases handle whitespace
  differently, and pybars3-rs reproduces the one that is installed: 0.9.7's
  whitespace control (`{{~tag~}}`) and removal of lines of block tags, or
  0.9.6's cleaning of the whitespace around standalone blocks.
* **pybars' quirks are kept**, because a drop-in must not change any output:
  [docs/parity.md](docs/parity.md) lists the surprising ones (an unclosed tag
  at the end of a template is silently dropped, error messages report the last
  line of the template, keyword argument names need two characters, ...).
* **CPython 3.10 to 3.15**, including free-threaded 3.14. pybars classifies
  characters with `str.isalpha()` and friends, and `repr()` escapes what
  `str.isprintable()` rejects, so its output depends on the interpreter's
  Unicode database. pybars3-rs has tables for Unicode 13.0 to 17.0, generated
  from each CPython by [`tools/gen_tables.py`](tools/gen_tables.py), and the
  Python package uses the running interpreter's.

## Performance

CPU time per call with pybars3 0.9.7 on CPython 3.12 (x86-64), from
[`tests/test_benchmark.py`](tests/test_benchmark.py) on order email
templates. "Validate" adds Python's `compile()` of the generated module,
which costs the same with both and dominates pybars3-rs' time on large
templates.

| Template | pybars `precompile()` | pybars3-rs | speedup | pybars validate | pybars3-rs validate | speedup |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 B | 7.2 ms | 0.014 ms | 510x | 7.9 ms | 0.54 ms | 15x |
| 1.3 KB | 89 ms | 0.12 ms | 750x | 94 ms | 4.0 ms | 23x |
| 10 KB | 660 ms | 0.97 ms | 680x | 700 ms | 30 ms | 23x |
| 50 KB | 3.4 s | 5.3 ms | 640x | 3.5 s | 190 ms | 19x |

The compiler is linear in the template length, including on inputs where a
backtracking parser rescans text, and on the whitespace runs where 0.9.7's
regular expressions are quadratic (`cargo bench` and `tests/test_stress.py`
have those).

## How it works

pybars runs two PyMeta grammars: `handlebars_grammar` parses the template into
a tree, and `compile_grammar` walks the tree and calls a `CodeBuilder` that
writes the Python module. In between, pybars3 0.9.6 drops the whitespace around
standalone block tags from the tree; pybars3 0.9.7 instead rewrites the text
with regular expressions before parsing it. The crate ports each step:

| pybars | pybars3-rs |
| --- | --- |
| `handlebars_grammar` | [`grammar/`](compiler/src/grammar): one method per rule, with the rule as its doc comment |
| PyMeta's runtime: ordered choice, lookahead, the memo, and `currentError`, the furthest position any rule reached, which decides whether pybars reports a syntax error and where | [`runtime.rs`](compiler/src/runtime.rs): only what changes pybars' result |
| `Compiler.whitespace_control` (0.9.7) | [`whitespace_control.rs`](compiler/src/whitespace_control.rs): the regular expressions' matches, computed in one linear pass |
| `Compiler.clean_whitespace` (0.9.6) | [`whitespace.rs`](compiler/src/whitespace.rs), index arithmetic included |
| `compile_grammar`, `CodeBuilder`, `FunctionContainer` | [`codegen.rs`](compiler/src/codegen.rs) |
| `repr()`, `int()`, `str.isalpha()`, `re`'s `\w` and `\s` | [`pyrepr.rs`](compiler/src/pyrepr.rs), [`chars.rs`](compiler/src/chars.rs) and the generated [`tables.rs`](compiler/src/tables.rs) |

PyMeta re-runs rules at the same position many times, and pybars is quadratic
on some inputs (unmatched `[` in a path, for example). The port computes the
same result in linear time, by remembering failures as PyMeta does and
scanning text runs in one step. [docs/architecture.md](docs/architecture.md)
maps every rule and method of pybars to its Rust counterpart.

## Verification

Byte-for-byte parity is the contract, and it is checked against pybars itself,
on every supported CPython in CI, for the pybars of this repository and for
pybars3 0.9.6:

| Check | What |
| --- | --- |
| [`tests/test_pybars_acceptance.py`](tests/test_pybars_acceptance.py) | pybars' own tests, with `pybars_rs.Compiler` as `pybars.Compiler` and every compile compared with pybars |
| [`tests/test_bounded_exhaustive.py`](tests/test_bounded_exhaustive.py) | every template of up to 3 characters over one character of each class that the grammar, the whitespace control and CPython's predicates tell apart (254,080 templates) |
| [`tests/test_differential_fuzz.py`](tests/test_differential_fuzz.py), [`tests/test_properties.py`](tests/test_properties.py) | 20,000 random templates built from real templates and syntax errors, and Hypothesis strategies shaped by pybars' grammar |
| [`tests/test_recursion.py`](tests/test_recursion.py) | `RecursionError` parity at every recursion limit around both pybars' boundary and the one where pybars3-rs starts compiling on its own |
| [`tests/test_harness.py`](tests/test_harness.py) | mutants of pybars, which the comparison must notice |
| [`tests/test_stress.py`](tests/test_stress.py) | linear time on adversarial inputs, no leaks, threads, the GIL is released |
| `cargo test` | unit tests, property tests, and corpora of pybars' results ([`golden.rs`](compiler/tests/golden.rs)) that need no Python |

`python -m tests.parity --fuzz 1000000` runs a longer campaign, and
`python -m tests.parity --corpus DIR` compares every template in a directory,
printing only hashes and metadata, which is safe for private templates.

## Security

pybars compiles templates to Python code and runs it, and pybars3-rs generates
the same code. Treat templates as code: compile only templates you trust, as
you would with pybars.

## Development

pybars3-rs is tested against the pybars it reproduces, which is the one of this
repository by default. From this directory:

```bash
pip install .. -r ci/requirements-01-maturin.txt -r ci/requirements-02-hypothesis.txt
pip install --no-build-isolation -e .
python tests.py
```

The editable install builds the extension module into `pybars_rs/`, in release
mode, because the tests compare speeds. Rebuild it after changing the Rust
code. `--no-deps` keeps the pybars3 that is installed: pybars3-rs would
otherwise replace a pybars3 newer than the ones it supports. To run a specific test:

```bash
python tests.py TestSeedCorpus.test_seed_templates_match_pybars
```

To test against pybars3 0.9.6 instead, install it and give the tests its test
suite, from its tag:

```bash
pip install pybars3==0.9.6
mkdir -p /tmp/pybars3-0.9.6 && git -C .. archive 0.9.6 tests | tar -x -C /tmp/pybars3-0.9.6
PYBARS_TESTS=/tmp/pybars3-0.9.6/tests python tests.py
```

The Rust code has its own tests and linters (the minimum supported Rust
version is 1.85):

```bash
cargo test
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
python -m flake8
```

A few environment variables make the Python tests longer:

| Variable | Effect |
| --- | --- |
| `EXHAUSTIVE_MAX_LENGTH=3` | every template of up to 3 characters (CI runs this; the weekly run does 4, in `EXHAUSTIVE_PARTS` parts) |
| `FUZZ_ITERATIONS=20000` | random templates per seed in `test_differential_fuzz.py` |
| `HYPOTHESIS_PROFILE=long` | 20,000 examples per property |
| `BENCHMARK=1` | print the speedups that `test_benchmark.py` measures |

`cargo +nightly fuzz run precompile` (in `fuzz/`) fuzzes the crate for panics.
A fix for a parity bug should add the template that shows it to `SEED_CORPUS`
in `tests/corpus.py`, and to the golden corpora by running
`tools/gen_golden.py`.

### When pybars/_compiler.py changes

The Rust compiler is only used with the `pybars/_compiler.py` files it was
verified against, whose SHA-256 are in `_PYBARS_COMPILERS` in
`pybars_rs/__init__.py`. Any change to that file makes pybars3-rs fall back to
pybars, and its tests fail with "pybars._compiler differs from the files
pybars_rs was verified against". Then:

1. Add the SHA-256 of the new file to `_PYBARS_COMPILERS`, with the release
   whose compiler it has, and run the tests: they compare the Rust compiler
   with the changed pybars. A change to the runtime only (`resolve()`, the
   helpers) passes as it is.
2. If the tests show that the generated code changed, port the change to
   `compiler/` as well, as a new `PybarsVersion` when it goes into a release.

### Generated files

* `compiler/src/tables.rs` comes from the Unicode databases of CPython 3.10
  to 3.15: `python3 tools/gen_tables.py` (it needs
  [uv](https://docs.astral.sh/uv/), which downloads the interpreters).
* `compiler/tests/golden/pybars-<version>.jsonl` come from pybars itself:
  `python tools/gen_golden.py` on CPython 3.12, with each pybars release
  installed (and `PYBARS_TESTS` for 0.9.6, as above).
* The recursion bound of the extension module (`BASE_FRAMES` and
  `FRAMES_PER_LEVEL` in `native/src/recursion.rs`) comes from
  `tools/calibrate_recursion.py`, run on every supported CPython.

CI checks that all of them are up to date.

### Releasing

1. Update `version` in `Cargo.toml` (the crate and the Python package share
   it), and the changelog.
2. Push a tag `pybars3-rs-vX.Y.Z`. The `pybars3-rs release` workflow builds the
   wheels and the source distribution, tests the wheels as installed, and
   publishes them to PyPI with
   [trusted publishing](https://docs.pypi.org/trusted-publishers/), from the
   `pypi` environment of this repository.

[PyMeta]: https://github.com/wbond/pymeta3
