//! pybars' results for about a thousand templates per release, recorded
//! from pybars3 0.9.6 and 0.9.7 on CPython 3.12 by `tools/gen_golden.py`:
//! the crate must reproduce each one. The generated modules are recorded as
//! a hash and a length; on a mismatch, the Python tests (`python tests.py`)
//! show the difference.

#![forbid(unsafe_code)]
#![allow(missing_docs)]

use pybars3_compiler::{Error, Fallback, Options, PybarsVersion, UnicodeVersion, precompile};
use serde_json::Value;

/// The 64-bit FNV-1a hash of the UTF-8 bytes of `text`, as hex.
fn fnv1a(text: &str) -> String {
    let hash = text.bytes().fold(0xcbf2_9ce4_8422_2325_u64, |hash, byte| {
        (hash ^ u64::from(byte)).wrapping_mul(0x0100_0000_01b3)
    });
    format!("{hash:016x}")
}

fn check_corpus(version: PybarsVersion, corpus: &str) {
    let options = Options::new(version, UnicodeVersion::V15_0);
    let mut failures = Vec::new();
    let mut count = 0;
    for line in corpus.lines() {
        let entry: Value = serde_json::from_str(line).expect("a JSON line");
        let source = entry["source"].as_str().expect("a source");
        let result = precompile(source, &options);
        let ok = match (&result, &entry) {
            (Ok(code), entry) if entry.get("code_fnv1a").is_some() => {
                Some(fnv1a(code).as_str()) == entry["code_fnv1a"].as_str()
                    && Some(code.len() as u64) == entry["code_len"].as_u64()
            }
            (Err(Error::Template(error)), entry) if entry.get("error").is_some() => {
                Some(error.message()) == entry["error"].as_str()
            }
            (Err(Error::Fallback(Fallback::IntConversion)), entry) => {
                entry["fallback"].as_str() == Some("int_conversion")
            }
            _ => false,
        };
        if !ok {
            failures.push(format!("{source:?}: pybars {entry}, pybars3-rs {result:?}"));
        }
        count += 1;
    }
    assert!(count > 900, "the corpus has only {count} templates");
    assert!(
        failures.is_empty(),
        "{} of {count} templates differ from pybars {version}:\n{}",
        failures.len(),
        failures[..failures.len().min(10)].join("\n")
    );
}

#[test]
fn the_crate_reproduces_pybars_0_9_6() {
    check_corpus(
        PybarsVersion::V0_9_6,
        include_str!("golden/pybars-0.9.6.jsonl"),
    );
}

#[test]
fn the_crate_reproduces_pybars_0_9_7() {
    check_corpus(
        PybarsVersion::V0_9_7,
        include_str!("golden/pybars-0.9.7.jsonl"),
    );
}

#[test]
fn the_hash_is_fnv1a() {
    assert_eq!(fnv1a(""), "cbf29ce484222325");
    assert_eq!(fnv1a("a"), "af63dc4c8601ec8c");
}
