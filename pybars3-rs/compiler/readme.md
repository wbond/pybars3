# pybars3-compiler

A port of [pybars3]'s Handlebars template compiler to Rust.

pybars compiles a Handlebars template to Python source code, which it then
runs. `pybars3_compiler::precompile` returns what
`pybars.Compiler().precompile(source)` returns, byte for byte, or the error
that pybars raises, hundreds of times faster. It reproduces pybars3 0.9.6 and
0.9.7 (the master branch has 0.9.7's compiler). The crate has no dependencies
and no `unsafe` code.

```rust
use pybars3_compiler::{Options, PybarsVersion, UnicodeVersion};

// pybars3 0.9.7 on CPython 3.12, whose Unicode database is 15.0.0.
let options = Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0);

let code = pybars3_compiler::precompile("Hello {{name}}!", &options).unwrap();
assert!(code.starts_with("import pybars\n"));
assert!(code.contains("    result.append('Hello ')\n"));

let error = pybars3_compiler::precompile("{{#if a}}{{/each}}", &options).unwrap_err();
assert_eq!(error.to_string(), "Error at character 16 of line 1 near {{/each}}");
```

The generated code imports pybars' runtime, so it is meant to be run by Python
with the same pybars3 release installed. Most users want the pybars3-rs Python
package, a drop-in replacement for `pybars.Compiler` built on this crate (see
[the readme of pybars3-rs](../readme.md)).

## API

* `precompile(source, &options)` returns the generated module, or an `Error`:
  * `Error::Template`: pybars raises `PybarsError` with this message (a syntax
    error, or a partial with two positional arguments);
  * `Error::Fallback`: pybars' result depends on CPython itself (an integer
    literal that `int()` rejects, or nesting deeper than
    `Options::nesting_limit`): run pybars to get it.
* `Options` describes the pybars to reproduce: its release (`PybarsVersion`,
  0.9.6 or 0.9.7, whose whitespace handling differs), the Unicode database of
  the CPython that runs it (`UnicodeVersion`, 13.0 to 17.0 for CPython 3.10 to
  3.15), `sys.get_int_max_str_digits()`, and the nesting limit. The two
  versions have no default, because the output depends on them.
* `PybarsVersion::header()` is the text that every module generated for the
  release starts with.

The minimum supported Rust version is 1.85.

[pybars3]: https://github.com/wbond/pybars3
