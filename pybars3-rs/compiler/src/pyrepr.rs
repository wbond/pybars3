//! The Python value formatting that pybars' generated code depends on:
//! `repr(str)`, and `str(int(text))` for integer literals.

use std::fmt::Write as _;

use crate::chars::Chars;

/// `int()` never checks the limit on strings of up to this many digits
/// (CPython's `_PY_LONG_MAX_STR_DIGITS_THRESHOLD`).
const INT_MAX_STR_DIGITS_THRESHOLD: usize = 640;

/// Why `int(text)` raises `ValueError`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum IntError {
    /// A character that `str.isdigit()` accepts but `int()` does not (`²`).
    NotDecimal,
    /// More digits than `sys.get_int_max_str_digits()` allows.
    TooManyDigits,
}

/// CPython's `repr()` of a `str`.
pub(crate) fn repr_str(text: &str, chars: Chars) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    repr_into(&mut out, text, chars);
    out
}

/// Append CPython's `repr()` of `text` to `out`.
pub(crate) fn repr_into(out: &mut String, text: &str, chars: Chars) {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    out.reserve(text.len() + 2);
    out.push(quote);
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            _ if c == quote => {
                out.push('\\');
                out.push(c);
            }
            _ if chars.is_printable(c) => out.push(c),
            _ => {
                let cp = u32::from(c);
                // Writing to a String cannot fail.
                let _ = match cp {
                    0..=0xff => write!(out, "\\x{cp:02x}"),
                    0x100..=0xffff => write!(out, "\\u{cp:04x}"),
                    _ => write!(out, "\\U{cp:08x}"),
                };
            }
        }
    }
    out.push(quote);
}

/// `str(int(text))` for `text` = an optional `-` and `str.isdigit()`
/// characters, as pybars' `integer` rule builds it, with
/// `sys.get_int_max_str_digits()` = `max_digits` (0: no limit).
pub(crate) fn int_str(text: &str, chars: Chars, max_digits: usize) -> Result<String, IntError> {
    let (negative, digits) = match text.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, text),
    };
    let mut value = String::with_capacity(digits.len() + 1);
    let mut count = 0;
    for c in digits.chars() {
        let digit = chars.decimal_value(c).ok_or(IntError::NotDecimal)?;
        count += 1;
        if value.is_empty() && digit == 0 {
            continue;
        }
        value.push(char::from_digit(digit, 10).ok_or(IntError::NotDecimal)?);
    }
    if count > INT_MAX_STR_DIGITS_THRESHOLD && max_digits > 0 && count > max_digits {
        return Err(IntError::TooManyDigits);
    }
    Ok(match (negative, value.is_empty()) {
        (_, true) => "0".to_owned(),
        (true, false) => format!("-{value}"),
        (false, false) => value,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::UnicodeVersion;

    const CHARS: Chars = Chars::new(UnicodeVersion::V15_0);

    fn repr(text: &str) -> String {
        repr_str(text, CHARS)
    }

    fn int(text: &str) -> Result<String, IntError> {
        int_str(text, CHARS, 4300)
    }

    #[test]
    fn repr_quotes_like_python() {
        assert_eq!(repr(""), "''");
        assert_eq!(repr("it's"), "\"it's\"");
        assert_eq!(repr("'\""), "'\\'\"'");
        assert_eq!(repr("\""), "'\"'");
        assert_eq!(repr("\\"), "'\\\\'");
    }

    #[test]
    fn repr_escapes_unprintable() {
        assert_eq!(repr("a\u{85}\t"), "'a\\x85\\t'");
        assert_eq!(repr("\x00\x7f"), "'\\x00\\x7f'");
        assert_eq!(repr("\u{a0}é"), "'\\xa0é'");
        assert_eq!(repr("\u{2028}"), "'\\u2028'");
        assert_eq!(repr("\u{e0001}😀"), "'\\U000e0001😀'");
    }

    #[test]
    fn int_like_python() {
        assert_eq!(int("0").unwrap(), "0");
        assert_eq!(int("-0").unwrap(), "0");
        assert_eq!(int("-007").unwrap(), "-7");
        assert_eq!(int("-12").unwrap(), "-12");
        assert_eq!(int("٣").unwrap(), "3");
        assert_eq!(int("1²"), Err(IntError::NotDecimal));
    }

    #[test]
    fn the_digit_limit_is_an_interpreter_setting() {
        assert_eq!(int(&"1".repeat(4300)).unwrap().len(), 4300);
        assert_eq!(int(&"1".repeat(4301)), Err(IntError::TooManyDigits));
        // Leading zeros count, as in CPython.
        assert_eq!(int(&"0".repeat(4301)), Err(IntError::TooManyDigits));
        assert_eq!(
            int_str(&"1".repeat(641), CHARS, 640),
            Err(IntError::TooManyDigits)
        );
        assert!(int_str(&"1".repeat(640), CHARS, 640).is_ok());
        // `int()` does not check strings of up to 640 digits at all.
        assert!(int_str(&"1".repeat(600), CHARS, 100).is_ok());
        assert!(int_str(&"1".repeat(5000), CHARS, 0).is_ok());
    }
}
