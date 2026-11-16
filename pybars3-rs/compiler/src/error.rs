//! Why [`precompile`](crate::precompile) returns no code.

use std::fmt;

use crate::chars::Chars;

/// Why [`precompile`](crate::precompile) returned no code.
///
/// ```
/// use pybars3_compiler::{Error, Options, PybarsVersion, UnicodeVersion};
///
/// let options = Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0);
/// match pybars3_compiler::precompile("{{#each items}}", &options) {
///     Ok(code) => println!("{code}"),
///     // pybars raises `PybarsError(error.message())`.
///     Err(Error::Template(error)) => eprintln!("PybarsError: {error}"),
///     // Run pybars itself to get its result.
///     Err(Error::Fallback(reason)) => eprintln!("run pybars: {}", reason.name()),
///     Err(error) => eprintln!("{error}"),
/// }
/// ```
#[derive(Debug, Clone, PartialEq, Eq)]
#[non_exhaustive]
pub enum Error {
    /// pybars rejects the template: it raises `pybars.PybarsError` with
    /// this message.
    Template(TemplateError),
    /// pybars' result for this template depends on CPython itself, which
    /// the port does not reproduce: run pybars to get it.
    Fallback(Fallback),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Template(error) => error.fmt(f),
            Error::Fallback(fallback) => fallback.fmt(f),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Error::Template(error) => Some(error),
            Error::Fallback(_) => None,
        }
    }
}

/// A template that pybars rejects with `PybarsError`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TemplateError {
    message: String,
    position: Option<usize>,
}

impl TemplateError {
    pub(crate) fn new(message: String, position: Option<usize>) -> Self {
        TemplateError { message, position }
    }

    /// The message of pybars' `PybarsError`, such as `Error at character 3
    /// of line 1 near {{a}`.
    #[must_use]
    pub fn message(&self) -> &str {
        &self.message
    }

    /// For a syntax error, where in the template the parse failed, in
    /// characters (Unicode scalar values) from the start.
    ///
    /// This is PyMeta's error position, from which pybars computes the
    /// character number in its message. pybars' line number is the number
    /// of lines of the whole template, not the line of this position.
    ///
    /// pybars3 0.9.7 parses the template after its whitespace control has
    /// rewritten it, and so the position and the message are those of the
    /// rewritten text.
    ///
    /// ```
    /// use pybars3_compiler::{Error, Options, PybarsVersion, UnicodeVersion};
    ///
    /// let options = Options::new(PybarsVersion::V0_9_7, UnicodeVersion::V15_0);
    /// let Err(Error::Template(error)) = pybars3_compiler::precompile("a\n{{b}\nc", &options) else {
    ///     panic!("a syntax error");
    /// };
    /// // pybars reports the last line of the template, not the second.
    /// assert_eq!(error.message(), "Error at character 4 of line 3 near {{b}");
    /// assert_eq!(error.position(), Some(5));
    /// ```
    #[must_use]
    pub fn position(&self) -> Option<usize> {
        self.position
    }
}

impl fmt::Display for TemplateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for TemplateError {}

/// Why pybars' result depends on CPython itself.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[non_exhaustive]
pub enum Fallback {
    /// An integer literal that `int()` rejects: a character that
    /// `str.isdigit()` accepts but is not a decimal digit (such as `²`), or
    /// more digits than `sys.get_int_max_str_digits()` allows. pybars raises
    /// `ValueError`.
    IntConversion,
    /// Nesting deeper than [`Options::nesting_limit`](crate::Options::nesting_limit).
    /// Depending on the stack depth it is called at, pybars may raise
    /// `RecursionError`.
    NestingDepth,
}

impl Fallback {
    /// A short name for the reason, for metrics: `int_conversion` or
    /// `nesting_depth`.
    ///
    /// ```
    /// assert_eq!(pybars3_compiler::Fallback::IntConversion.name(), "int_conversion");
    /// ```
    #[must_use]
    pub const fn name(self) -> &'static str {
        match self {
            Fallback::IntConversion => "int_conversion",
            Fallback::NestingDepth => "nesting_depth",
        }
    }
}

impl fmt::Display for Fallback {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Fallback::IntConversion => "int() rejects an integer literal: run pybars",
            Fallback::NestingDepth => "the template is nested too deeply: run pybars",
        })
    }
}

/// pybars' syntax error for an error at `position`.
pub(crate) fn syntax_error(text: &[char], position: usize, chars: Chars) -> TemplateError {
    // line_num = source.count('\n') + 1
    let line = text.iter().filter(|&&c| c == '\n').count() + 1;
    // beginning_of_line = source.rfind('\n', 0, position)
    let character = match text[..position].iter().rposition(|&c| c == '\n') {
        Some(newline) => position - newline,
        None => position,
    };
    let word = extract_word(text, position, chars);
    TemplateError::new(
        format!("Error at character {character} of line {line} near {word}"),
        Some(position),
    )
}

/// `Compiler._extract_word`: the text around `position` up to whitespace or
/// a brace.
fn extract_word(text: &[char], position: usize, chars: Chars) -> String {
    // re.search('{{|{|\s|$', source[:position][::-1])
    let before: Vec<char> = text[..position].iter().rev().copied().collect();
    let start_offset = boundary(&before, '{', chars);
    // re.search('}}|}|\s|$', source[position:])
    let end_offset = boundary(&text[position..], '}', chars);
    text[position - start_offset..position + end_offset]
        .iter()
        .collect()
}

/// The offset that `_extract_word` takes from `re.search('BB|B|\s|$', text)`:
/// the match's end for a brace, its start otherwise.
fn boundary(text: &[char], brace: char, chars: Chars) -> usize {
    for (index, &c) in text.iter().enumerate() {
        if c == brace {
            let doubled = text.get(index + 1) == Some(&brace);
            return index + if doubled { 2 } else { 1 };
        }
        if chars.is_space(c) {
            return index;
        }
    }
    text.len()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::UnicodeVersion;

    fn word(text: &str, position: usize) -> String {
        let text: Vec<char> = text.chars().collect();
        extract_word(&text, position, Chars::new(UnicodeVersion::LATEST))
    }

    #[test]
    fn the_word_extends_to_braces_and_spaces() {
        assert_eq!(word("{{a}", 3), "{{a}");
        assert_eq!(word("x {{#if a b}}", 6), "{{#if");
        assert_eq!(word("ab cd", 4), "cd");
        assert_eq!(word("{a}}", 2), "{a}}");
        assert_eq!(word("", 0), "");
    }

    #[test]
    fn messages_are_displayed_as_pybars_raises_them() {
        let error = Error::Template(TemplateError::new("boom".into(), None));
        assert_eq!(error.to_string(), "boom");
        assert!(std::error::Error::source(&error).is_some());
        for fallback in [Fallback::IntConversion, Fallback::NestingDepth] {
            let error = Error::Fallback(fallback);
            assert!(error.to_string().ends_with(": run pybars"), "{error}");
            assert!(std::error::Error::source(&error).is_none());
        }
        assert_eq!(Fallback::IntConversion.name(), "int_conversion");
        assert_eq!(Fallback::NestingDepth.name(), "nesting_depth");
    }
}
