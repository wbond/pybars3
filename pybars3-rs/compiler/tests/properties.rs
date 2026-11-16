//! Property tests: what holds for every input. Byte-for-byte parity with
//! pybars is checked against pybars itself by the Python test suite
//! (`tests/` next to this crate) and by `golden.rs`.

#![forbid(unsafe_code)]
#![allow(missing_docs, clippy::unwrap_used)]

use proptest::prelude::*;
use pybars3_compiler::{Error, Fallback, Options, PybarsVersion, UnicodeVersion};

/// pybars3 0.9.7 on CPython 3.12.
const OPTIONS: Options = Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0);

fn precompile(source: &str) -> Result<String, Error> {
    pybars3_compiler::precompile(source, &OPTIONS)
}

/// `options` for every supported pybars3 release.
fn every_release(options: Options) -> impl Iterator<Item = Options> {
    PybarsVersion::ALL
        .into_iter()
        .map(move |version| Options::new(version, options.unicode_version()))
}

fn precompile_with(source: &str, options: &Options) -> Result<String, Error> {
    pybars3_compiler::precompile(source, options)
}

/// Pieces that exercise every grammar rule, and characters that each rule
/// tells apart.
const PIECES: &[&str] = &[
    "{{",
    "}}",
    "{{{",
    "}}}",
    "{{#",
    "{{^",
    "{{/",
    "{{>",
    "{{!",
    "{{&",
    "{{{{",
    "else",
    "if",
    "each",
    "a",
    "ab",
    "a.b",
    "../",
    "@../",
    "@index",
    "[",
    "]",
    "(",
    ")",
    "=",
    "\"",
    "'",
    "\\",
    "-1",
    "12",
    "true",
    "false",
    "null",
    "undefined",
    " ",
    "\t",
    "\n",
    "\r\n",
    "²",
    "٣",
    "é",
    "\u{2028}",
    "~",
    "{{~",
    "~}}",
    "{{#a}}\n",
    "\n{{/a}}",
    "  {{else}}\r\n",
    "this",
    "/",
    ".",
    "x",
];

fn ascii_template() -> impl Strategy<Value = String> {
    let ascii: Vec<&str> = PIECES
        .iter()
        .copied()
        .filter(|piece| piece.is_ascii())
        .collect();
    prop::collection::vec(prop::sample::select(ascii), 0..24).prop_map(|pieces| pieces.concat())
}

fn template() -> impl Strategy<Value = String> {
    prop::collection::vec(prop::sample::select(PIECES), 0..24).prop_map(|pieces| pieces.concat())
}

fn template_without_tildes_or_newlines() -> impl Strategy<Value = String> {
    let pieces: Vec<&str> = PIECES
        .iter()
        .copied()
        .filter(|piece| !piece.contains(['~', '\n']))
        .collect();
    prop::collection::vec(prop::sample::select(pieces), 0..24).prop_map(|pieces| pieces.concat())
}

/// Templates built from complete tags, nested: most of them compile.
fn well_formed() -> impl Strategy<Value = String> {
    let leaf = prop::sample::select(
        &[
            "text",
            " ",
            "\n",
            "  \n",
            "\r\n",
            "{{name}}",
            "{{{a.b}}}",
            "{{&c}}",
            "{{this}}",
            "{{../up}}",
            "{{[a'b]}}",
            "{{a.[b c]}}",
            "{{! note }}",
            "{{foo ab=1 cd=\"s\" -3 true null}}",
            "{{foo (bar baz=(q 1)) 'x\\'y'}}",
            "{{> part}}",
            "{{> part ctx ab=1 ab=2}}",
            "{{> (dyn x) ab=c}}",
            "{{> part 1 2}}",
            "{{{{raw a}}}}{{x}}{{{{/raw}}}}",
            "{{@index}}",
        ][..],
    )
    .prop_map(str::to_owned);
    leaf.prop_recursive(4, 48, 6, |inner| {
        (
            prop::sample::select(&["#if a", "#each xs", "^unless b", "#with c dd=1"][..]),
            prop::collection::vec(inner.clone(), 0..4),
            prop::option::of(prop::collection::vec(inner, 0..3)),
            prop::sample::select(&["", "\n", "  \n"][..]),
        )
            .prop_map(|(open, body, alt, pad)| {
                let name = open[1..].split(' ').next().unwrap();
                let alt = alt.map_or(String::new(), |alt| format!("{{{{else}}}}{}", alt.concat()));
                format!(
                    "{pad}{{{{{open}}}}}{pad}{}{alt}{pad}{{{{/{name}}}}}{pad}",
                    body.concat()
                )
            })
    })
}

fn is_partial_error(error: &Error) -> bool {
    matches!(error, Error::Template(e) if e.message() == "An extra positional argument was passed to a partial")
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(2000))]

    #[test]
    fn well_formed_templates_compile(parts in prop::collection::vec(well_formed(), 1..5)) {
        let source = parts.concat();
        for options in every_release(OPTIONS) {
            match precompile_with(&source, &options) {
                Ok(code) => prop_assert!(code.contains("def render(")),
                Err(error) => prop_assert!(
                    is_partial_error(&error) || error == Error::Fallback(Fallback::NestingDepth),
                    "{error:?}"
                ),
            }
        }
    }
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(3000))]

    #[test]
    fn grammar_shaped_templates_compile_or_fail_like_pybars(source in template()) {
        for options in every_release(OPTIONS) {
            match precompile_with(&source, &options) {
                Ok(code) => {
                    prop_assert!(code.starts_with(options.pybars_version().header()));
                    prop_assert!(code.ends_with("    if called:\n        result = str(result)\n    return result\n"));
                }
                Err(Error::Template(error)) => prop_assert!(
                    error.message().starts_with("Error at character ")
                        || error.message() == "An extra positional argument was passed to a partial",
                    "{error:?}"
                ),
                Err(Error::Fallback(_)) => {}
                Err(error) => prop_assert!(false, "unexpected {error:?}"),
            }
        }
    }

    #[test]
    fn any_text_is_handled_and_deterministic(source in any::<String>()) {
        for options in every_release(OPTIONS) {
            prop_assert_eq!(precompile_with(&source, &options), precompile_with(&source, &options));
        }
    }

    /// pybars3 0.9.7 only rewrites `~` marks and lines, and 0.9.6 only
    /// cleans the whitespace around tags on lines of their own.
    #[test]
    fn the_releases_agree_without_tildes_or_newlines(source in template_without_tildes_or_newlines()) {
        let generated = |version: PybarsVersion| {
            let options = Options::new(version, OPTIONS.unicode_version());
            precompile_with(&source, &options).map(|code| code[version.header().len()..].to_owned())
        };
        prop_assert_eq!(generated(PybarsVersion::V0_9_6), generated(PybarsVersion::V0_9_7));
    }

    #[test]
    fn text_without_braces_is_only_literals(source in "[^{]{1,40}") {
        let code = precompile(&source).unwrap();
        prop_assert!(!code.contains("resolve("));
        prop_assert!(code.contains("result.append("));
    }

    #[test]
    fn ascii_templates_do_not_depend_on_the_unicode_version(source in "[ -~\t\n\r]{0,40}") {
        for pybars in PybarsVersion::ALL {
            let reference = precompile_with(&source, &Options::new(pybars, UnicodeVersion::LATEST));
            for version in UnicodeVersion::ALL {
                let options = Options::new(pybars, version);
                prop_assert_eq!(&precompile_with(&source, &options), &reference);
            }
        }
    }

    #[test]
    fn grammar_shaped_templates_agree_across_unicode_versions_on_ascii(source in ascii_template()) {
        for pybars in PybarsVersion::ALL {
            let reference = precompile_with(&source, &Options::new(pybars, UnicodeVersion::LATEST));
            for version in UnicodeVersion::ALL {
                let options = Options::new(pybars, version);
                prop_assert_eq!(&precompile_with(&source, &options), &reference);
            }
        }
    }

    #[test]
    fn a_lower_nesting_limit_only_adds_fallbacks(
        parts in prop::collection::vec(well_formed(), 1..4),
        limit in 0..Options::MAX_NESTING_LIMIT,
    ) {
        let source = parts.concat();
        for options in every_release(OPTIONS) {
            let full = precompile_with(&source, &options);
            let limited = precompile_with(&source, &options.with_nesting_limit(limit));
            prop_assert!(limited == full || limited == Err(Error::Fallback(Fallback::NestingDepth)));
            if limited == Err(Error::Fallback(Fallback::NestingDepth)) {
                // A smaller limit than the one that failed fails too.
                for lower in 0..limit {
                    prop_assert_eq!(
                        precompile_with(&source, &options.with_nesting_limit(lower)),
                        Err(Error::Fallback(Fallback::NestingDepth))
                    );
                }
            }
        }
    }

    #[test]
    fn the_digit_limit_only_adds_fallbacks(digits in "[0-9]{600,700}", limit in 640usize..700) {
        let source = format!("{{{{foo {digits}}}}}");
        let unlimited = precompile_with(&source, &OPTIONS.with_int_max_str_digits(0));
        prop_assert!(unlimited.is_ok());
        let limited = precompile_with(&source, &OPTIONS.with_int_max_str_digits(limit));
        if digits.len() > limit {
            prop_assert_eq!(limited, Err(Error::Fallback(Fallback::IntConversion)));
        } else {
            prop_assert_eq!(limited, unlimited);
        }
    }
}

/// The port recurses once per nesting level, and the nesting limit bounds
/// the native stack it needs: the deepest templates compile on a thread with
/// a small stack (CPython's threads get the platform default, which is
/// 512 KiB on macOS and can be 128 KiB with musl).
#[test]
fn the_deepest_templates_fit_on_a_small_stack() {
    let depth = Options::MAX_NESTING_LIMIT - 1;
    let shapes = [
        "{{#if a}}".repeat(depth) + "x" + &"{{/if}}".repeat(depth),
        "{{#if a}}x{{else}}".repeat(depth) + "y" + &"{{/if}}".repeat(depth),
        "{{foo ".to_owned() + &"(bar kk=".repeat(depth) + "a" + &")".repeat(depth) + "}}",
        "{{> ".to_owned() + &"(bar ".repeat(depth) + "a" + &")".repeat(depth) + "}}",
        "{{#if a}}".repeat(depth) + "x",
    ];
    let stack = if cfg!(debug_assertions) { 256 } else { 64 } * 1024;
    std::thread::Builder::new()
        .stack_size(stack)
        .spawn(move || {
            for source in &shapes {
                let result = precompile(source);
                assert!(
                    !matches!(result, Err(Error::Fallback(_))),
                    "{source}: {result:?}"
                );
            }
        })
        .unwrap()
        .join()
        .unwrap();
}
