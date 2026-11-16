//! Print the Python module that pybars generates for a template.
//!
//! ```text
//! cargo run --example precompile -- template.hbs [PYBARS_VERSION [UNICODE_VERSION]]
//! echo 'Hello {{name}}' | cargo run --example precompile -- - 0.9.6
//! ```

#![forbid(unsafe_code)]
#![allow(clippy::print_stdout, clippy::print_stderr)]

use std::io::Read as _;
use std::process::ExitCode;

use pybars3_compiler::{Error, Options, PybarsVersion, UnicodeVersion};

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let source = match args.next() {
        Some(path) if path != "-" => match std::fs::read_to_string(&path) {
            Ok(source) => source,
            Err(error) => {
                eprintln!("{path}: {error}");
                return ExitCode::from(2);
            }
        },
        _ => {
            let mut source = String::new();
            if let Err(error) = std::io::stdin().read_to_string(&mut source) {
                eprintln!("stdin: {error}");
                return ExitCode::from(2);
            }
            source
        }
    };
    let pybars = match args.next().map(|version| version.parse::<PybarsVersion>()) {
        None => PybarsVersion::LATEST,
        Some(Ok(version)) => version,
        Some(Err(error)) => {
            eprintln!(
                "{error}; supported: {:?}",
                PybarsVersion::ALL.map(PybarsVersion::as_str)
            );
            return ExitCode::from(2);
        }
    };
    let unicode = match args.next().map(|version| version.parse::<UnicodeVersion>()) {
        None => UnicodeVersion::LATEST,
        Some(Ok(version)) => version,
        Some(Err(error)) => {
            eprintln!(
                "{error}; supported: {:?}",
                UnicodeVersion::ALL.map(UnicodeVersion::as_str)
            );
            return ExitCode::from(2);
        }
    };
    match pybars3_compiler::precompile(&source, &Options::new(pybars, unicode)) {
        Ok(code) => {
            print!("{code}");
            ExitCode::SUCCESS
        }
        Err(Error::Template(error)) => {
            eprintln!("pybars.PybarsError: {error}");
            ExitCode::FAILURE
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}
