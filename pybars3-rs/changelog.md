# changelog

## 0.1.0

- First release: pybars3's template compiler, ported to Rust (the
  `pybars3-compiler` crate), and `pybars_rs.Compiler`, a drop-in replacement
  for `pybars.Compiler` that runs on it
- Reproduces pybars3 0.9.6 and 0.9.7 byte for byte, including 0.9.7's
  whitespace control, on CPython 3.10 to 3.15 and free-threaded CPython 3.14
- Falls back to pybars where its result depends on CPython itself (`int()`,
  the recursion limit, lone surrogates, `str` subclasses, `pybars._compiler.debug`);
  `counters()`, `is_available()` and `unavailable_reason()` report it
