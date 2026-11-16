//! `cargo +nightly fuzz run precompile`: any text, for every supported
//! pybars3 release and Unicode version, compiles or fails cleanly, never
//! panics, and the result is deterministic.

#![no_main]
#![forbid(unsafe_code)]

use libfuzzer_sys::fuzz_target;
use pybars3_compiler::{Error, Options, PybarsVersion, UnicodeVersion};

fuzz_target!(|data: &[u8]| {
    let Some((&selector, rest)) = data.split_first() else {
        return;
    };
    let Ok(source) = std::str::from_utf8(rest) else {
        return;
    };
    let selector = usize::from(selector);
    let pybars = PybarsVersion::ALL[selector % PybarsVersion::ALL.len()];
    let unicode = UnicodeVersion::ALL[(selector >> 1) % UnicodeVersion::ALL.len()];
    let options = Options::new(pybars, unicode).with_nesting_limit(selector >> 4);
    let result = pybars3_compiler::precompile(source, &options);
    match &result {
        Ok(code) => assert!(code.starts_with(pybars.header())),
        Err(Error::Template(error)) => assert!(!error.message().is_empty()),
        Err(_) => {}
    }
    assert_eq!(result, pybars3_compiler::precompile(source, &options));
});
