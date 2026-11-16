//! A port of [pybars3]'s Handlebars template compiler to Rust.
//!
//! pybars compiles a Handlebars template to Python source code, which it
//! then runs. [`precompile`] returns what `pybars.Compiler().precompile(source)`
//! returns, byte for byte, or the error pybars raises, in a small fraction of
//! the time:
//!
//! ```
//! use pybars3_compiler::{Options, PybarsVersion, UnicodeVersion};
//!
//! // pybars3 0.9.7 on CPython 3.12, whose Unicode database is 15.0.0.
//! let options = Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0);
//!
//! let code = pybars3_compiler::precompile("Hello {{name}}!", &options).unwrap();
//! assert!(code.starts_with("import pybars\n"));
//! assert!(code.contains("    result.append('Hello ')\n"));
//!
//! let error = pybars3_compiler::precompile("{{#if a}}{{/each}}", &options).unwrap_err();
//! assert_eq!(
//!     error.to_string(),
//!     "Error at character 16 of line 1 near {{/each}}",
//! );
//! ```
//!
//! The generated code imports pybars' runtime (`pybars._compiler`), so it is
//! meant to be run by Python with the same pybars3 release installed. The
//! `pybars3-rs` Python package wraps this crate as a drop-in replacement for
//! `pybars.Compiler`.
//!
//! # Compatibility
//!
//! The output is pybars' output, quirks included: whitespace handling,
//! syntax error messages and positions, and the code generated for every
//! construct. `docs/parity.md` in the repository lists the surprising cases,
//! and `docs/architecture.md` maps pybars' code to this crate's.
//!
//! [`Options`] says which pybars to reproduce: pybars3 0.9.6 or 0.9.7, whose
//! whitespace handling differs ([`PybarsVersion`]), and the CPython that
//! runs it. pybars classifies characters with CPython's `str` methods, whose
//! answers depend on the interpreter's Unicode database, and parses integer
//! literals with `int()`, whose limit on digits is an interpreter setting.
//! Neither version has a default, because the output depends on them.
//!
//! # Fallbacks
//!
//! In two cases pybars' result depends on CPython itself rather than on
//! pybars' code, and [`precompile`] returns [`Error::Fallback`] instead of
//! guessing: an integer literal that `int()` rejects (pybars raises
//! `ValueError`), and nesting deep enough that pybars could reach Python's
//! recursion limit. Callers then run pybars, which the Python package does
//! automatically.
//!
//! [pybars3]: https://github.com/wbond/pybars3

#![forbid(unsafe_code)]

mod chars;
mod codegen;
mod error;
mod grammar;
mod options;
mod pyrepr;
mod runtime;
mod tables;
mod tree;
mod whitespace;
mod whitespace_control;

pub use error::{Error, Fallback, TemplateError};
pub use options::{
    Options, PybarsVersion, UnicodeVersion, UnknownPybarsVersion, UnknownUnicodeVersion,
};

// The examples of the crate's readme are tested too.
#[cfg(doctest)]
#[doc = include_str!("../readme.md")]
struct ReadmeDoctests;

/// Compile `source` the way `pybars.Compiler().precompile(source)` does, for
/// the pybars release and on the CPython that `options` describe.
///
/// # Errors
///
/// [`Error::Template`] when pybars raises `PybarsError`, and
/// [`Error::Fallback`] when pybars' result depends on CPython itself.
///
/// ```
/// use pybars3_compiler::{Error, Fallback, Options, PybarsVersion, UnicodeVersion};
///
/// let options = Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0);
/// let code = pybars3_compiler::precompile("{{x 12}}", &options).unwrap();
/// assert!(code.contains("value = value(context, 12)"));
///
/// // `int('²')` raises ValueError in pybars: run pybars to get its exception.
/// assert_eq!(
///     pybars3_compiler::precompile("{{x ²}}", &options),
///     Err(Error::Fallback(Fallback::IntConversion)),
/// );
/// ```
pub fn precompile(source: &str, options: &Options) -> Result<String, Error> {
    let chars = chars::Chars::new(options.unicode_version());
    let mut text: Vec<char> = source.chars().collect();
    let version = options.pybars_version();
    // pybars3 0.9.7 rewrites the text before parsing it, and reports syntax
    // errors in the rewritten text.
    if version == PybarsVersion::V0_9_7 {
        text = whitespace_control::whitespace_control(&text, chars);
    }
    let parsed = grammar::parse(&text, chars, options).map_err(Error::Fallback)?;
    let mut tree = parsed.tree;
    if version == PybarsVersion::V0_9_6 {
        whitespace::clean_whitespace(&mut tree);
    }
    if parsed.error_position < text.len() {
        return Err(Error::Template(error::syntax_error(
            &text,
            parsed.error_position,
            chars,
        )));
    }
    codegen::full_code(&tree, chars, version).map_err(|codegen::ExtraPositionalArgument| {
        Error::Template(TemplateError::new(
            "An extra positional argument was passed to a partial".to_owned(),
            None,
        ))
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn precompile_for(version: PybarsVersion, source: &str) -> Result<String, Error> {
        super::precompile(source, &Options::new(version, UnicodeVersion::V15_0))
    }

    fn precompile(source: &str) -> Result<String, Error> {
        precompile_for(PybarsVersion::LATEST, source)
    }

    #[test]
    fn syntax_errors_report_pybars_line_and_word() {
        for version in PybarsVersion::ALL {
            let error = precompile_for(version, "line1\nline2 {{/x}}\nline3\nline4").unwrap_err();
            assert_eq!(
                error.to_string(),
                "Error at character 9 of line 4 near {{/x}}"
            );
            let Error::Template(error) = error else {
                panic!("not a template error")
            };
            assert_eq!(error.position(), Some(14));
        }
    }

    #[test]
    fn unclosed_tags_at_the_end_are_dropped_like_pybars() {
        let code = precompile("abc {{foo").unwrap();
        assert!(code.contains("result.append('abc ')"));
        assert!(!code.contains("foo"));
    }

    #[test]
    fn integers_that_int_rejects_fall_back() {
        assert_eq!(
            precompile("{{foo ²}}"),
            Err(Error::Fallback(Fallback::IntConversion))
        );
    }

    #[test]
    fn deep_nesting_falls_back() {
        let deep = "{{#if a}}".repeat(30) + &"{{/if}}".repeat(30);
        assert_eq!(
            precompile(&deep),
            Err(Error::Fallback(Fallback::NestingDepth))
        );
    }

    #[test]
    fn every_module_starts_with_the_header_of_its_release() {
        for version in PybarsVersion::ALL {
            assert!(
                precompile_for(version, "")
                    .unwrap()
                    .starts_with(version.header())
            );
        }
        assert_ne!(
            PybarsVersion::V0_9_6.header(),
            PybarsVersion::V0_9_7.header()
        );
    }

    #[test]
    fn whitespace_depends_on_the_release() {
        let standalone = "{{#if a}}\nbody\n{{/if}}\n";
        let code = precompile_for(PybarsVersion::V0_9_6, standalone).unwrap();
        assert!(code.contains("result.append('body\\n')"), "{code}");
        let code = precompile_for(PybarsVersion::V0_9_7, standalone).unwrap();
        assert!(code.contains("result.append('body')"), "{code}");

        // Whitespace control is pybars3 0.9.7's, and its syntax errors are
        // positioned in the rewritten text.
        assert_eq!(
            precompile_for(PybarsVersion::V0_9_6, "a {{~b~}} c")
                .unwrap_err()
                .to_string(),
            "Error at character 4 of line 1 near {{~b~}}"
        );
        let code = precompile_for(PybarsVersion::V0_9_7, "a {{~b~}} c").unwrap();
        assert!(code.contains("result.append('a')"), "{code}");
        assert!(code.contains("result.append('c')"), "{code}");
        assert_eq!(
            precompile_for(PybarsVersion::V0_9_7, "{{a}}\n  {{~b}")
                .unwrap_err()
                .to_string(),
            "Error at character 8 of line 1 near {{b}"
        );
    }

    #[test]
    fn extra_positional_partial_arguments_are_errors() {
        assert_eq!(
            precompile("{{> part a b}}").unwrap_err().to_string(),
            "An extra positional argument was passed to a partial"
        );
    }
}
