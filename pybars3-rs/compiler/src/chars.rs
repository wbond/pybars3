//! CPython's `str` predicates for one character, as PyMeta's built-in rules
//! and pybars' regular expressions apply them.
//!
//! The answers for ASCII are the same in every Unicode version and need no
//! table; other characters are looked up in [`crate::tables`], generated
//! from each supported CPython.

use std::cmp::Ordering;

use crate::UnicodeVersion;
use crate::tables;

/// The predicates of one Unicode version.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Chars {
    bit: u8,
}

/// The mask of the table range that contains `c`, or 0.
fn mask(table: &[(u32, u32, u8)], c: char) -> u8 {
    let cp = u32::from(c);
    table
        .binary_search_by(|&(start, end, _)| {
            if end < cp {
                Ordering::Less
            } else if start > cp {
                Ordering::Greater
            } else {
                Ordering::Equal
            }
        })
        .map_or(0, |index| table[index].2)
}

impl Chars {
    pub(crate) const fn new(version: UnicodeVersion) -> Self {
        Chars { bit: version.bit() }
    }

    fn lookup(self, table: &[(u32, u32, u8)], c: char) -> bool {
        mask(table, c) & self.bit != 0
    }

    /// `c.isalpha()`: PyMeta's `letter`.
    pub(crate) fn is_alpha(self, c: char) -> bool {
        if c.is_ascii() {
            c.is_ascii_alphabetic()
        } else {
            self.lookup(&tables::ALPHA, c)
        }
    }

    /// `c.isalnum()`. PyMeta's `letterOrDigit` also accepts `_`, and so does
    /// the `\w` of Python's `re` ([`Chars::is_word`]).
    pub(crate) fn is_alnum(self, c: char) -> bool {
        if c.is_ascii() {
            c.is_ascii_alphanumeric()
        } else {
            self.lookup(&tables::ALNUM, c)
        }
    }

    /// `\w` in a Python `str` pattern: `c.isalnum() or c == '_'`.
    pub(crate) fn is_word(self, c: char) -> bool {
        c == '_' || self.is_alnum(c)
    }

    /// `c.isdigit()`: PyMeta's `digit`. Wider than what `int()` accepts.
    pub(crate) fn is_digit(self, c: char) -> bool {
        if c.is_ascii() {
            c.is_ascii_digit()
        } else {
            self.lookup(&tables::DIGIT, c)
        }
    }

    /// `c.isspace()`: PyMeta's `spaces`, and `\s` in a Python `str` pattern.
    pub(crate) fn is_space(self, c: char) -> bool {
        if c.is_ascii() {
            matches!(
                c,
                ' ' | '\t' | '\n' | '\r' | '\x0b' | '\x0c' | '\x1c'..='\x1f'
            )
        } else {
            self.lookup(&tables::SPACE, c)
        }
    }

    /// `c.isprintable()`, which decides what `repr()` escapes.
    pub(crate) fn is_printable(self, c: char) -> bool {
        if c.is_ascii() {
            (' '..='~').contains(&c)
        } else {
            self.lookup(&tables::PRINTABLE, c)
        }
    }

    /// The value `int()` gives a decimal digit (`c.isdecimal()`), or `None`
    /// when `int()` rejects the character.
    pub(crate) fn decimal_value(self, c: char) -> Option<u32> {
        if c.is_ascii_digit() {
            return Some(u32::from(c) - u32::from('0'));
        }
        if c.is_ascii() {
            return None;
        }
        let cp = u32::from(c);
        let index = tables::DECIMAL.partition_point(|&(start, _, _)| start <= cp);
        let &(start, end, versions) = tables::DECIMAL.get(index.checked_sub(1)?)?;
        (cp <= end && versions & self.bit != 0).then_some((cp - start) % 10)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn every() -> impl Iterator<Item = Chars> {
        UnicodeVersion::ALL.into_iter().map(Chars::new)
    }

    #[test]
    fn ascii_and_tables_agree_at_the_boundary() {
        for chars in every() {
            for c in (0u8..=127).map(char::from) {
                assert_eq!(chars.is_alpha(c), chars.lookup(&tables::ALPHA, c), "{c:?}");
                assert_eq!(chars.is_alnum(c), chars.lookup(&tables::ALNUM, c), "{c:?}");
                assert_eq!(chars.is_digit(c), chars.lookup(&tables::DIGIT, c), "{c:?}");
                assert_eq!(chars.is_space(c), chars.lookup(&tables::SPACE, c), "{c:?}");
                assert_eq!(
                    chars.is_printable(c),
                    chars.lookup(&tables::PRINTABLE, c),
                    "{c:?}"
                );
                assert_eq!(
                    chars.decimal_value(c).is_some(),
                    chars.lookup(&tables::DECIMAL, c),
                    "{c:?}"
                );
            }
        }
    }

    #[test]
    fn decimal_values() {
        for chars in every() {
            assert_eq!(chars.decimal_value('7'), Some(7));
            assert_eq!(chars.decimal_value('\u{ff15}'), Some(5));
            assert_eq!(chars.decimal_value('\u{0bcd}'), None);
            assert_eq!(chars.decimal_value('\u{2160}'), None);
            assert_eq!(chars.decimal_value('a'), None);
            assert_eq!(chars.decimal_value('²'), None);
            assert!(chars.is_digit('²'));
            // Five runs of mathematical digits in one table range.
            assert_eq!(chars.decimal_value('\u{1d7ce}'), Some(0));
            assert_eq!(chars.decimal_value('\u{1d7ff}'), Some(9));
        }
    }

    #[test]
    fn answers_differ_between_versions() {
        // U+1FAE9, an emoji added in Unicode 16.0: printable from CPython
        // 3.14, escaped by `repr()` before.
        let face = '\u{1fae9}';
        assert!(!Chars::new(UnicodeVersion::V15_1).is_printable(face));
        assert!(Chars::new(UnicodeVersion::V16_0).is_printable(face));
        // U+1E4F0..U+1E4F9, Nag Mundari digits, added in Unicode 15.0.
        assert_eq!(
            Chars::new(UnicodeVersion::V14_0).decimal_value('\u{1e4f3}'),
            None
        );
        assert_eq!(
            Chars::new(UnicodeVersion::V15_0).decimal_value('\u{1e4f3}'),
            Some(3)
        );
    }

    #[test]
    fn tables_are_sorted_and_disjoint() {
        for table in [
            &tables::ALPHA[..],
            &tables::ALNUM[..],
            &tables::DIGIT[..],
            &tables::SPACE[..],
            &tables::PRINTABLE[..],
            &tables::DECIMAL[..],
        ] {
            for pair in table.windows(2) {
                assert!(pair[0].0 <= pair[0].1 && pair[0].1 < pair[1].0, "{pair:x?}");
            }
            assert!(table.iter().all(|&(_, _, versions)| versions != 0));
        }
    }
}
