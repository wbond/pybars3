# Architecture: how pybars3-rs reproduces pybars

This is a map for maintainers, especially ones who don't know PyMeta. It
explains how pybars compiles a template, where each piece lives in
pybars3-rs, and the semantics that a change must preserve.
[parity.md](parity.md) lists the observable behaviour; this file explains the
code.

## pybars, step by step

`pybars.Compiler()._generate_code(source)` (`pybars/_compiler.py`) is what
`compile()`, `precompile()` and `template()` share:

0. **Whitespace control** (pybars3 0.9.7). `whitespace_control(source)`
   rewrites the text with regular expressions: it applies the `~` marks of
   `{{~tag~}}` and removes the lines that hold only block tags. The steps
   below work on the rewritten text, error messages included.
1. **Parse.** `handlebars_grammar` is a PyMeta grammar (a PEG with actions).
   PyMeta compiles it to a Python class at import time and runs it, building a
   tree of tuples: `['template', ('literal', 'Hello '), ('escapedexpand',
   ('path', ['name']), []), ...]`. It also returns `currentError`, the furthest
   position that any step reached.
2. **Clean whitespace** (pybars3 0.9.6). `clean_whitespace(tree)` removes the
   whitespace and newline around block tags that stand alone on their line.
3. **Check.** If `currentError` is before the end of the text, pybars raises
   `PybarsError("Error at character C of line L near WORD")`.
4. **Generate.** `compile_grammar`, a second PyMeta grammar, walks the tree and
   calls a `CodeBuilder`, which writes the Python module: a `render` function
   and one `block_N` function per nested template, after a fixed header.

pybars3-rs does the same steps in `compiler/src/lib.rs::precompile`, as
`Options::pybars_version` says.

## The map

| pybars3 / PyMeta3 0.5.1 | pybars3-rs | Notes |
| --- | --- | --- |
| `handlebars_grammar` (41 rules used) | `grammar/mod.rs` (templates, tags, blocks), `grammar/args.rs` (arguments, paths, literals) | One method per rule, with pybars' rule as its doc comment. pybars also defines `other` and `pathfinish`, which no rule uses. |
| PyMeta's `OMetaBase` (`pymeta/runtime.py`): `_apply`, `_or` (also used for `x?`), `_not`, `many` (also for `x+`), `pred`, `exactly`, `considerError` | `runtime.rs`: `apply`, `choice`, `optional`, `not`, `many`, `many1`, `pred`, `exactly`, `consider` | Only what changes pybars' result, see below |
| PyMeta's built-in rules `rule_anything`, `letter`, `letterOrDigit`, `digit`, `eatWhitespace` (`spaces`) | `runtime.rs` (`anything`, `letter`, `letter_or_digit`, `digit`, `spaces`), with the predicates of `chars.rs` | `str.isalpha()` & co. come from the generated `tables.rs`, one bit per Unicode version |
| `Compiler.whitespace_control` (0.9.7) | `whitespace_control.rs` | The matches of the regular expressions, which match in at most one way, computed in one linear pass |
| `Compiler.clean_whitespace` (0.9.6) | `whitespace.rs` | Same index arithmetic, same limits (only `#` blocks, only their main branch) |
| `_generate_code`'s error check, `_extract_word` | `lib.rs::precompile`, `error.rs::syntax_error` | |
| `compile_grammar`: `compile`, `prolog`, `rule`, `block`, `invertedblock`, `rawblock`, `partial`, `literal`, `expand`, `escapedexpand`, `comment` | `codegen.rs`: `Builder::compile`, `start`, `rule`, `block`, `raw_block`, `partial`, `expand` | |
| `compile_grammar`: `path`, `complexarg`, `arg`, `pathseg` | `codegen.rs`: `resolve_call`, `complex_arg`, `arg_code`, `compiled_segment` | |
| `CodeBuilder` (`start`, `finish`, `add_*`, `find_lookup`, `arguments_to_call`, `_wrap_nested`) | `codegen.rs`: `Builder` and its methods | Writes strings directly instead of lists of lines |
| `FunctionContainer.full_code` | `codegen.rs::header`, `full_code` | The header names the release |
| `repr()` of the literal text, `int()` of integer literals | `pyrepr.rs` | `int()` failures become `Fallback::IntConversion` |
| `Compiler._generate_code`, as a method | `native/src/generate_code.rs::GenerateCode`, bound by `pybars_rs/__init__.py::Compiler` | Falls back to pybars' own method |
| (Python's recursion limit) | `native/src/recursion.rs` | When the port may compile, and how pybars is called |

## The PyMeta semantics that decide pybars' output

The tree is the easy part. pybars' **error position**, and therefore whether a
template is a syntax error at all, comes from PyMeta's bookkeeping, and the
port reproduces it exactly. `runtime.rs` documents each rule; in short:

* **`currentError` is a maximum.** Every step passes the error it returned
  to `considerError`, which keeps the furthest. Consuming a character
  considers its index; `spaces` considers the last character it looked at; a
  negative lookahead that succeeded, and an optional that matched nothing,
  consider the current position; an ordered choice considers the furthest
  failure of the alternatives that failed before the one that matched. That is
  why `abc {{foo` is not an error: a rule that failed at the end of the text
  moved `currentError` to the end.
* **Failures are memoized, and a remembered failure has no position.** When
  a rule fails at a position, PyMeta leaves a `LeftRecursion` marker there,
  and applying the rule there again fails with position `None`. This changes
  error positions (`{{#if a}}x{{else}y{{/if}}` reports character 16, not 17).
  The port keeps one bit per (rule, position) in `Parser::failed`: hence the
  compile-time check that the rules fit in 64 bits.
* **Successes are not memoized.** Rules are pure, so running one again gives
  the same result and only considers positions that were already considered.
* **Text runs and bracketed segments are done in one step.** `other_text` is
  `(~<start> <anything>)+`, one PyMeta step per character, and
  `notclosebracket+` rescans from every `[`. The port jumps to the next `{{`
  or `]`, and then records exactly what those steps would have: the memo
  markers at every position, the furthest position, and the failing last
  iteration. That makes pybars3-rs linear where pybars is quadratic.

When you change the grammar code, check the error positions, not just the
output: the seed corpus, the exhaustive tests and the fuzzers compare both.

## Character classes and the CPython version

pybars uses CPython's `str.isalpha()`, `isalnum()`, `isdigit()`, `isspace()`
and `isprintable()` (through PyMeta's built-in rules, `repr()`, and the `\w` and
`\s` of its regular expressions), and `int()` for decimal digits. Their answers
depend on the interpreter's Unicode database. `tools/gen_tables.py` asks
CPython 3.10 to 3.15 for every code point and writes `tables.rs`: one list of
ranges per predicate, each range with a bit set of the Unicode versions it
holds for. ASCII never needs a table.

`Options` takes the Unicode version explicitly. The Python package passes
`unicodedata.unidata_version`, and refuses to run on a version it has no
tables for.

## The whitespace control of pybars3 0.9.7

pybars3 0.9.7's `re.sub` has five alternatives, and Python's `re` backtracks,
but on these expressions each alternative matches in at most one way:
`[^{}]+` stops at the first brace, a tag needs `}}` right after it, and a run
of tags ends at a `{` or a blank, where the line break or `$` that follows the
run cannot match. So `whitespace_control.rs` tries the alternatives in order at
each position, takes the longest run of tags, and measures each whitespace run
once, which keeps the pass linear where `\s*{{~` makes Python's quadratic.
The replacement is pybars' too: the match stripped of `str.isspace()`
characters, without the `~` marks and the blanks between tags.

## The Python package

`pybars_rs/__init__.py` makes `pybars_rs.Compiler`, a subclass of
`pybars.Compiler` whose `_generate_code` is the native `GenerateCode`. It is
bound with `types.MethodType`, so that calling it adds no Python frame.

* **Fast path.** It copies the `str` out, releases the GIL, runs the crate,
  and returns pybars' own `FunctionContainer`, or raises `PybarsError` with the
  crate's message. A panic is caught and falls back to pybars.
* **Fallback.** For anything the crate does not reproduce (a `Fallback`, a
  non-`str` source, lone surrogates, pybars' `debug` flag, a panic), it calls
  `pybars.Compiler._generate_code` from native code, so pybars runs at the
  stack depth it would have had without pybars3-rs. pybars keeps its code builder
  on the class, so each fallback gets a builder of its own instead: a subclass
  of pybars' compile grammar whose `globals`, where PyMeta looks up `builder`
  for the grammar's actions, holds a new `CodeBuilder`. The native code takes
  one from a small pool and sets it in a `ContextVar` that
  `pybars_rs.Compiler._compiler` reads, then calls pybars. No lock is needed, so
  fallbacks run concurrently and nest (a `str` subclass may compile templates
  while pybars parses it), and no PyMeta grammar is ever built, which would
  cost 70 ms and recurse deeply.
* **Recursion.** pybars recurses in Python, so whether a deep template
  compiles depends on the caller's stack depth. `recursion.rs` measures the
  headroom (Python frames from 3.12; units of the counter shared with native
  calls on 3.10 and 3.11) and lets the crate compile only what pybars would
  compile too, using a bound calibrated by `tools/calibrate_recursion.py`. On
  3.10 and 3.11 it also gives back the unit that its own native call took,
  around the fallback: that is the only `unsafe` code in the project.
* **Guards.** The package uses the crate only with the `pybars/_compiler.py`
  and PyMeta3 0.5.1 files it was verified against (SHA-256), on CPython with a
  supported Unicode version, and after a self-check against recorded digests
  of pybars' output. The digest of `pybars/_compiler.py` also says which
  release's compiler it has. Otherwise `pybars_rs.Compiler` is pybars'
  compiler.

## Performance notes

* One pass over the benchmark templates (61 KB) takes 2.9 s with pybars, 5.1
  ms with a plain release build of the crate, 5.0 ms with the fat LTO of the
  release profile, and 4.5 ms with profile-guided optimization. PGO is not
  used: through Python its gain disappears into the call overhead and CPython's
  `compile()` of the generated module.
* Most of what remains is the PEG bookkeeping itself (memo bits, error
  positions), which parity requires.
