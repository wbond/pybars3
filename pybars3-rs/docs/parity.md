# Parity with pybars3

pybars3-rs' contract is pybars' output: the same generated source, byte for byte,
or the same exception with the same message. pybars' surprising behaviour is
therefore **kept, not fixed**: code that caches generated source, compares it,
or shows pybars' error messages to users must not see a difference.

This file lists the behaviour that a reimplementation is most likely to get
wrong, each with an input that shows it. The oracle is the installed pybars,
on PyMeta3 0.5.1: pybars3 0.9.7 (tag `0.9.7`, and the master branch, which has
the same compiler) or pybars3 0.9.6 (tag `0.9.6`). Unless an item says
otherwise, the two releases behave the same. Every item is covered by the seed
corpus of [`tests/corpus.py`](../tests/corpus.py), which the test suite
compares with pybars on every supported CPython.

## The generated source

`precompile()` returns pybars' module, header included: `import pybars`, a
check that `pybars.__version__` is the release that generated it (`'0.9.7'`),
the runtime imports, then `render()` and the `block_N` functions of nested
templates, each preceded by the functions it references.
`PybarsVersion::header()` is that header.

* An empty `{{else}}` is still a branch: `{{#if a}}x{{else}}{{/if}}` generates
  an empty `block_2` and passes it as `inverse`, while `{{#if a}}x{{/if}}`
  passes `lambda this: None`.
* `{{this}}` looks up `helpers.get(u'')` and `resolve(context, u'')`, and has
  no `helperMissing` branch (its name is empty). The compile grammar maps the
  path segments `/`, `.`, `` and `this` to the empty string, so `{{a.b}}` is
  `resolve(context, u'a', u'', u'b')`.
* `../` becomes `@_parent` and `@../` becomes `@@_parent`:
  `{{@../index}}` is `resolve(context, u'@@_parent', u'index')`.
* A subexpression's helper name is its path segments joined together:
  `{{foo (a.b x)}}` calls the helper `ab`.
* Path segments in brackets are pasted into the generated code as they are,
  without escaping: `{{a.[b'c]}}` generates `u'b'c'`, which Python then
  rejects when the module is compiled.
* Partial arguments are split into keyword and positional arguments with
  `re.match(r'(\w+)=(.+)$', argument)` on the generated argument code, with
  CPython's Unicode `\w`. A repeated keyword keeps its first position and its
  last value, and a second positional argument raises
  `PybarsError("An extra positional argument was passed to a partial")`.
* Literal text is written with CPython's `repr()`, which escapes the
  characters that `str.isprintable()` rejects (`\x85`, `\u2028`,
  `\U000e0001`), depending on the interpreter's Unicode version.

## Syntax errors

pybars raises `Error at character C of line L near WORD` when PyMeta's
`currentError`, the furthest position any rule reached, is before the end of
the template.

* The line number is the number of lines of the **whole template**, not the
  line of the error: `line1\nline2 {{/x}}\nline3` reports line 3.
* The character number is relative to the start of the line of the error.
* An unclosed tag or block at the end of a template is **dropped without an
  error**, because a rule that failed at the end of the text moved
  `currentError` there: `abc {{foo` and `abc {{#if a}} xyz` both render `abc `.
* `{{[}}` compiles, for the same reason.
* `WORD` extends from the error to the nearest brace or whitespace on each
  side (`Compiler._extract_word`).
* PyMeta remembers that a rule failed at a position, and applying it there
  again fails without a position. This moves the error: `{{#if a}}x{{else}y{{/if}}`
  reports character 16, not 17.
* pybars3 0.9.7 parses, and reports errors in, the text that its whitespace
  control produced: `{{a}}\n  {{~b}` reports `Error at character 8 of line 1
  near {{b}`, not line 2.

## The grammar

* Keyword argument names need two or more characters: `{{foo a=1}}` is a
  syntax error, `{{foo ab=1}}` is not (`safesymbol` requires a first letter
  and then one or more letters or digits).
* An argument that starts with a literal is that literal, so the rest is a
  syntax error: `{{foo trueish}}`, `{{foo 12abc}}`.
* `letterOrDigit` accepts `_`, and symbols also accept `-` and `@`:
  `{{a_b}}`, `{{a-b}}`, `{{a@b}}`.
* `\r\n` at the start of a text run (at the start of the template, or right
  after a tag) becomes `\n`: `newline_text` keeps only the `\n`. Elsewhere a
  text run keeps `\r\n` as it is.
* A space between arguments is `' '`, `'\t'`, `'\r'` or `'\n'`, but the
  optional spaces inside a tag are anything `str.isspace()` accepts.
* An unmatched `[` in a path takes everything up to the next `]` or the end:
  `{{user.profile.[a.b.c.d}}` compiles. (pybars is quadratic on many of
  them; pybars3-rs is linear.)

## Integer literals

`integer ::= '-'? <digit>+ => int(...)`, where `digit` is `str.isdigit()`.

* Decimal digits of other scripts are converted: `{{x ٣}}` generates `3`.
* `-0` and `007` become `0` and `7`.
* Characters that `str.isdigit()` accepts but `int()` rejects make pybars raise
  `ValueError`: `{{foo ²}}`. So does a literal with more digits than
  `sys.get_int_max_str_digits()` (4300 by default; 0 disables the limit). The
  Rust crate returns `Fallback::IntConversion`, and the Python package runs
  pybars, which raises it.

## Whitespace

The two releases handle whitespace differently, and pybars3-rs reproduces the
one that is installed.

pybars3 0.9.7 rewrites the template before parsing it, with one `re.sub`
(`Compiler.whitespace_control`). Its matches, stripped of whitespace and of the
`~` marks and the blanks between tags, replace the text:

* `~}}` removes the whitespace after it, and `{{~` the whitespace before it,
  where whitespace is anything `str.isspace()` accepts (`\s`):
  `a {{~b~}} c` renders `aBc`.
* A line that holds only block tags (`{{#...}}`, `{{/...}}`, `{{!...}}`,
  `{{else}}` or `{{else if ...}}`, with spaces and tabs around them) loses its
  newline and its blanks; the tags of the line are joined.
* On the first line of the template, only `{{#...}}` and `{{!...}}` tags count,
  and on the last line, only `{{/...}}` and `{{!...}}`. Inverted blocks
  (`{{^...}}`) never do.
* The last line can be followed by one final `\n`, because `$` also matches
  before it: `a\n{{/b}}\n` becomes `a{{/b}}\n`, but `a\n{{/b}}\r\n` becomes
  `a\n{{/b}}`, through the rule of lines of tags.
* `\s*{{~` makes Python's regular expression quadratic on long whitespace
  runs; pybars3-rs computes the same matches in one linear pass.

pybars3 0.9.6 has no whitespace control: `{{~b~}}` is a syntax error. Its
`clean_whitespace` removes the whitespace and newlines around a block tag that
is alone on its line, from the parsed tree, with these limits, all kept:

* only `{{#...}}` blocks, not `{{^...}}` inverted blocks;
* only the main branch is cleaned recursively, not the `{{else}}` branch;
* after a close tag, the whitespace is removed but not the newline;
* a newline inside a text run is not a line of its own:
  `{{#if a}}\nbody\n{{/if}}\n` keeps `body\n`, where pybars3 0.9.7 keeps
  `body`.

## Recursion

pybars parses with Python recursion, so a template nested deeply enough raises
`RecursionError`, at a depth that depends on how deep the caller's stack is.
pybars3-rs compiles templates of up to 20 levels of nesting itself (the template
counts as one, and each block body, `{{else}}` branch or subexpression inside
it as one more), but only when the remaining stack headroom guarantees that
pybars would succeed too;
otherwise it runs pybars, from native code, at the stack depth pybars would
have had. On CPython 3.10 and 3.11, where Python frames and native calls share
one counter, it gives back the unit its own native call used. The outcome,
success or `RecursionError`, is therefore pybars' at every recursion limit
(`tests/test_recursion.py`).

Giving that unit back takes CPython's `Py_LeaveRecursiveCall` and
`Py_EnterRecursiveCall`, which PyO3 has no safe API for: these calls, in
`native/src/recursion.rs`, are the only `unsafe` code in pybars3-rs, and only
run on CPython 3.10 and 3.11 (the rest of the extension module denies `unsafe`,
and the crate forbids it). Without them, pybars3-rs would raise
`RecursionError` one frame before pybars on those two versions, for templates
nested deeply enough to reach the limit. Exact parity was preferred.

A fallback needs nothing that pybars itself does not: it runs pybars' own
grammars, which pybars built when it was imported, and only gives the call a
code builder of its own (see Concurrency). In particular it builds no PyMeta
grammar, which would recurse deeply, so a fallback works at every recursion
limit at which pybars does.

## Input types

* pybars3 0.9.6 parses a `str` subclass through the subclass's own methods
  (pybars3 0.9.7's `re.sub` turns it into a `str` first), and anything that is
  not a `str` makes pybars raise `PybarsError("Template source must be a
  unicode string")`: pybars3-rs runs pybars for both.
* Strings with lone surrogates (`"a\ud800b"`) cannot be represented in Rust;
  pybars3-rs runs pybars for them.

## Concurrency

pybars keeps its code builder on the `Compiler` class, so two threads that
compile at the same time can corrupt each other's output. When pybars3-rs
runs pybars, it gives the call a builder of its own: a subclass of pybars'
compile grammar whose `globals` (where PyMeta looks up `builder` for the
grammar's actions) holds a new `CodeBuilder`. pybars3-rs never touches pybars'
builder, so code that uses pybars directly is not affected, and since no two
calls share a builder, `pybars_rs.Compiler` is safe from any number of threads
without a lock. Calls also nest: code that compiles templates while pybars
compiles one (a `str` subclass's methods with pybars3 0.9.6, a
`whitespace_control` override with 0.9.7) gets the same results as with
pybars.
