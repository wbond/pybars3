//! The parts of PyMeta 0.5.1's runtime that decide what pybars' template
//! grammar returns, including the error position that pybars turns into a
//! syntax error.
//!
//! PyMeta keeps a `currentError`: every step of a rule passes the error it
//! returned to `considerError`, which keeps the one furthest into the input.
//! The steps that return something other than `currentError` itself are:
//!
//! * a character that `exactly`, `anything`, `letter`, ... consumed: its
//!   index;
//! * `spaces`: the index of the last character it looked at;
//! * a negative lookahead that succeeded, and an optional that matched
//!   nothing: the current position;
//! * an ordered choice that succeeded: the furthest failure position among
//!   the alternatives that failed before it.
//!
//! A failure carries a position too, and PyMeta's memo changes it: a rule
//! that failed at a position leaves its `LeftRecursion` marker behind, so the
//! next application of that rule there fails with position `None`.
//! [`Parser::apply`] reproduces that. Successful results are not memoized:
//! running a rule again gives the same result and only considers positions
//! that were already considered.

use crate::Fallback;
use crate::chars::Chars;

/// Identifies a rule for the failure memo (at most 64 rules).
pub(crate) type RuleId = u32;

/// Why a parse step did not produce a value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Stop {
    /// PyMeta's `ParseError`, with its position (`None` from a memo marker).
    Fail(Option<usize>),
    /// A Python exception or a limit: pybars' result is not reproduced.
    Fallback(Fallback),
}

/// The result of a parse step.
pub(crate) type P<T> = Result<T, Stop>;

/// Parser state over the template's characters.
pub(crate) struct Parser<'a> {
    pub(crate) text: &'a [char],
    /// The character predicates of the CPython being reproduced.
    pub(crate) chars: Chars,
    /// The deepest nesting to compile.
    pub(crate) nesting_limit: usize,
    /// `sys.get_int_max_str_digits()`.
    pub(crate) int_max_str_digits: usize,
    pub(crate) pos: usize,
    /// `currentError`'s position. It starts at the initial `nullError()`, 0.
    pub(crate) current_error: usize,
    /// Per position, the rules whose `LeftRecursion` marker is there.
    failed: Vec<u64>,
    pub(crate) depth: usize,
    /// For each position, the first `]` at or after it (or the end), built
    /// on first use by [`Parser::next_close_bracket`].
    close_brackets: Vec<usize>,
    /// For each position, the first `{{` at or after it (or the end), built
    /// on first use by [`Parser::next_start`].
    starts: Vec<usize>,
}

impl<'a> Parser<'a> {
    pub(crate) fn new(text: &'a [char], chars: Chars, options: &crate::Options) -> Self {
        Parser {
            text,
            chars,
            nesting_limit: options.nesting_limit(),
            int_max_str_digits: options.int_max_str_digits(),
            pos: 0,
            current_error: 0,
            failed: vec![0; text.len() + 1],
            depth: 0,
            close_brackets: Vec::new(),
            starts: Vec::new(),
        }
    }

    /// The first `{{` at or after `position`, or the end of the text.
    pub(crate) fn next_start(&mut self, position: usize) -> usize {
        if self.starts.is_empty() {
            let len = self.text.len();
            let mut next = len;
            self.starts = vec![len; len + 1];
            for index in (0..len).rev() {
                if self.text[index] == '{' && self.text.get(index + 1) == Some(&'{') {
                    next = index;
                }
                self.starts[index] = next;
            }
        }
        self.starts[position]
    }

    /// The first `]` at or after `position`, or the end of the text.
    pub(crate) fn next_close_bracket(&mut self, position: usize) -> usize {
        if self.close_brackets.is_empty() {
            let mut next = self.text.len();
            self.close_brackets = vec![next; self.text.len() + 1];
            for (index, &c) in self.text.iter().enumerate().rev() {
                if c == ']' {
                    next = index;
                }
                self.close_brackets[index] = next;
            }
        }
        self.close_brackets[position]
    }

    /// Whether `rule` left a failure marker at `position`.
    pub(crate) fn has_failed(&self, rule: RuleId, position: usize) -> bool {
        self.failed[position] & (1u64 << rule) != 0
    }

    /// Leave `rule`'s failure marker at `position`.
    pub(crate) fn mark_failed(&mut self, rule: RuleId, position: usize) {
        self.failed[position] |= 1u64 << rule;
    }

    /// `considerError` for an error at `position`.
    pub(crate) fn consider(&mut self, position: Option<usize>) {
        if let Some(position) = position {
            self.current_error = self.current_error.max(position);
        }
    }

    /// `self._apply(rule)` for a rule without arguments: memo markers only.
    pub(crate) fn apply<T>(&mut self, rule: RuleId, body: impl FnOnce(&mut Self) -> P<T>) -> P<T> {
        let position = self.pos;
        let bit = 1u64 << rule;
        if self.failed[position] & bit != 0 {
            return Err(Stop::Fail(None));
        }
        self.failed[position] |= bit;
        let result = body(self);
        if result.is_ok() {
            self.failed[position] &= !bit;
        }
        result
    }

    /// The next character, without consuming it; a failure at the end.
    fn head(&self) -> P<char> {
        self.text
            .get(self.pos)
            .copied()
            .ok_or(Stop::Fail(Some(self.text.len())))
    }

    /// Consume a character that `accept` accepts (`exactly`, `letter`, ...).
    pub(crate) fn char_if(&mut self, accept: impl FnOnce(char) -> bool) -> P<char> {
        let c = self.head()?;
        if !accept(c) {
            return Err(Stop::Fail(Some(self.pos)));
        }
        self.consider(Some(self.pos));
        self.pos += 1;
        Ok(c)
    }

    /// `exactly(c)` (not memoized).
    pub(crate) fn exactly(&mut self, wanted: char) -> P<char> {
        self.char_if(|c| c == wanted)
    }

    /// `'abc'` as a sequence of `exactly`.
    pub(crate) fn exactly_str(&mut self, wanted: &str) -> P<()> {
        wanted.chars().try_for_each(|c| self.exactly(c).map(drop))
    }

    /// The built-in `anything`.
    pub(crate) fn anything(&mut self) -> P<char> {
        self.apply(rules::ANYTHING, |p| p.char_if(|_| true))
    }

    /// The built-in `letter`.
    pub(crate) fn letter(&mut self) -> P<char> {
        self.apply(rules::LETTER, |p| {
            let chars = p.chars;
            p.char_if(|c| chars.is_alpha(c))
        })
    }

    /// The built-in `letterOrDigit`.
    pub(crate) fn letter_or_digit(&mut self) -> P<char> {
        self.apply(rules::LETTER_OR_DIGIT, |p| {
            let chars = p.chars;
            p.char_if(|c| c == '_' || chars.is_alnum(c))
        })
    }

    /// The built-in `digit`.
    pub(crate) fn digit(&mut self) -> P<char> {
        self.apply(rules::DIGIT, |p| {
            let chars = p.chars;
            p.char_if(|c| chars.is_digit(c))
        })
    }

    /// The built-in `spaces`: always succeeds.
    pub(crate) fn spaces(&mut self) -> P<()> {
        self.apply(rules::SPACES, |p| {
            let mut last = None;
            while let Some(&c) = p.text.get(p.pos) {
                last = Some(p.pos);
                if !p.chars.is_space(c) {
                    break;
                }
                p.pos += 1;
            }
            p.consider(last);
            Ok(())
        })
    }

    /// `~x`.
    pub(crate) fn not<T>(&mut self, x: impl FnOnce(&mut Self) -> P<T>) -> P<()> {
        let start = self.pos;
        match x(self) {
            Err(Stop::Fail(_)) => {
                self.pos = start;
                self.consider(Some(start));
                Ok(())
            }
            Err(stop) => Err(stop),
            Ok(_) => {
                let after = self.pos;
                self.pos = start;
                Err(Stop::Fail(Some(after)))
            }
        }
    }

    /// `x?`.
    pub(crate) fn optional<T>(&mut self, x: impl FnOnce(&mut Self) -> P<T>) -> P<Option<T>> {
        let start = self.pos;
        match x(self) {
            Ok(value) => Ok(Some(value)),
            Err(Stop::Fail(position)) => {
                self.pos = start;
                self.consider(position.max(Some(start)));
                Ok(None)
            }
            Err(stop) => Err(stop),
        }
    }

    /// `a | b | ...`: PyMeta's `_or`.
    pub(crate) fn choice<T>(&mut self, alternatives: &[fn(&mut Self) -> P<T>]) -> P<T> {
        let start = self.pos;
        let mut failed: Option<Option<usize>> = None;
        for alternative in alternatives {
            match alternative(self) {
                Ok(value) => {
                    if let Some(position) = failed {
                        self.consider(position);
                    }
                    return Ok(value);
                }
                Err(Stop::Fail(position)) => {
                    self.pos = start;
                    failed = Some(failed.map_or(position, |worst| worst.max(position)));
                }
                Err(stop) => return Err(stop),
            }
        }
        Err(Stop::Fail(failed.flatten()))
    }

    /// `x*`.
    pub(crate) fn many<T>(&mut self, mut x: impl FnMut(&mut Self) -> P<T>) -> P<Vec<T>> {
        let mut values = Vec::new();
        self.many_into(&mut values, &mut x)?;
        Ok(values)
    }

    /// `x+`.
    pub(crate) fn many1<T>(&mut self, mut x: impl FnMut(&mut Self) -> P<T>) -> P<Vec<T>> {
        let mut values = vec![x(self)?];
        self.many_into(&mut values, &mut x)?;
        Ok(values)
    }

    fn many_into<T>(
        &mut self,
        values: &mut Vec<T>,
        x: &mut impl FnMut(&mut Self) -> P<T>,
    ) -> P<()> {
        loop {
            let start = self.pos;
            match x(self) {
                Ok(value) => values.push(value),
                Err(Stop::Fail(_)) => {
                    self.pos = start;
                    return Ok(());
                }
                Err(stop) => return Err(stop),
            }
        }
    }

    /// `x+` over characters, collected into a `String` (`u''.join(x)`).
    pub(crate) fn many1_string(&mut self, mut x: impl FnMut(&mut Self) -> P<char>) -> P<String> {
        let mut text = String::from(x(self)?);
        loop {
            let start = self.pos;
            match x(self) {
                Ok(c) => text.push(c),
                Err(Stop::Fail(_)) => {
                    self.pos = start;
                    return Ok(text);
                }
                Err(stop) => return Err(stop),
            }
        }
    }

    /// `?(condition)`: a failure is at `currentError`.
    pub(crate) fn pred(&mut self, condition: bool) -> P<()> {
        if condition {
            Ok(())
        } else {
            Err(Stop::Fail(Some(self.current_error)))
        }
    }

    /// The `anything` that reads a rule argument from PyMeta's `ArgInput`:
    /// its error is the position of the input under it.
    pub(crate) fn take_argument(&mut self) {
        self.consider(Some(self.pos));
    }
}

/// Memo identifiers of the built-in rules; grammar rules follow.
pub(crate) mod rules {
    use super::RuleId;
    pub(crate) const ANYTHING: RuleId = 0;
    pub(crate) const LETTER: RuleId = 1;
    pub(crate) const LETTER_OR_DIGIT: RuleId = 2;
    pub(crate) const DIGIT: RuleId = 3;
    pub(crate) const SPACES: RuleId = 4;
    /// The first identifier free for grammar rules.
    pub(crate) const FIRST_GRAMMAR_RULE: RuleId = 5;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chars(text: &str) -> Vec<char> {
        text.chars().collect()
    }

    fn parser(text: &[char]) -> Parser<'_> {
        Parser::new(
            text,
            Chars::new(crate::UnicodeVersion::LATEST),
            &crate::Options::new(crate::PybarsVersion::LATEST, crate::UnicodeVersion::LATEST),
        )
    }

    #[test]
    fn a_failed_rule_fails_without_position_the_second_time() {
        let text = chars("x");
        let mut parser = parser(&text);
        assert_eq!(parser.letter_or_digit(), Ok('x'));
        assert_eq!(parser.anything(), Err(Stop::Fail(Some(1))));
        assert_eq!(parser.anything(), Err(Stop::Fail(None)));
    }

    #[test]
    fn an_optional_that_matches_nothing_considers_the_failure() {
        let text = chars("ab");
        let mut parser = parser(&text);
        parser.pos = 1;
        assert_eq!(parser.optional(|p| p.exactly_str("bc")), Ok(None));
        assert_eq!(parser.current_error, 2);
        assert_eq!(parser.pos, 1);
    }

    #[test]
    fn spaces_considers_the_last_character_it_saw() {
        let text = chars("  ");
        let mut parser = parser(&text);
        parser.spaces().unwrap();
        assert_eq!((parser.pos, parser.current_error), (2, 1));
    }

    #[test]
    fn choice_joins_failures() {
        let text = chars("ab");
        let mut parser = parser(&text);
        assert_eq!(
            parser.choice(&[|p| p.exactly_str("abc"), |p| p.exactly('x').map(drop)]),
            Err(Stop::Fail(Some(2)))
        );
        assert_eq!(
            parser.choice(&[|p| p.exactly_str("abc"), |p| p.exactly('a').map(drop)]),
            Ok(())
        );
        assert_eq!(parser.current_error, 2);
    }
}
