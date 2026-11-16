//! `Compiler.whitespace_control`: what pybars3 0.9.7 does to the text of a
//! template before parsing it.
//!
//! pybars replaces every match of one regular expression, left to right:
//!
//! ```text
//! ~}}\s*
//! | \s*{{~
//! | (?<=\n)([ \t]*{{(#[^{}]+|/[^{}]+|![^{}]+|else|else if [^{}]+)}}[ \t]*)+\r?\n
//! | ^([ \t]*{{(#[^{}]+|![^{}]+)}}[ \t]*)+\r?\n
//! | \r?\n([ \t]*{{(/[^{}]+|![^{}]+)}}[ \t]*)+$
//! ```
//!
//! with the match stripped of whitespace (`str.strip()`), from which a second
//! expression removes the `~` marks and the blanks between tags:
//!
//! ```text
//! (?<={{)~ | ~(?=}}) | (?<=}})[ \t]+(?={{)
//! ```
//!
//! Python's `re` backtracks, but on these expressions each alternative
//! matches in at most one way, which this module computes directly: the tag
//! sequences of the last three alternatives match when the longest run of
//! tags is followed by the line break (or end) that they need, because a
//! shorter run ends at a `{` or a blank. Whitespace runs are measured once,
//! so that the scan is linear where `\s*{{~` makes Python's quadratic.

use std::ops::Range;

use crate::chars::Chars;

/// `Compiler.whitespace_control(source)`, for the characters of `source`.
pub(crate) fn whitespace_control(text: &[char], chars: Chars) -> Vec<char> {
    let mut scanner = Scanner {
        text,
        chars,
        run: 0..0,
    };
    let mut output = Vec::with_capacity(text.len());
    let mut copied = 0;
    let mut start = 0;
    while start < text.len() {
        let Some(end) = scanner.match_at(start) else {
            start += 1;
            continue;
        };
        output.extend_from_slice(&text[copied..start]);
        clean_up(strip(&text[start..end], chars), &mut output);
        copied = end;
        start = end;
    }
    output.extend_from_slice(&text[copied..]);
    output
}

/// The tags that a line of tags may hold, in each of the last three
/// alternatives.
#[derive(Debug, Clone, Copy)]
enum Tags {
    /// `#[^{}]+|/[^{}]+|![^{}]+|else|else if [^{}]+`: a line of its own.
    Line,
    /// `#[^{}]+|![^{}]+`: the first line of the template.
    FirstLine,
    /// `/[^{}]+|![^{}]+`: the last line of the template.
    LastLine,
}

impl Tags {
    /// The characters that start a `X[^{}]+` tag.
    fn sigils(self) -> &'static [char] {
        match self {
            Tags::Line => &['#', '/', '!'],
            Tags::FirstLine => &['#', '!'],
            Tags::LastLine => &['/', '!'],
        }
    }
}

struct Scanner<'a> {
    text: &'a [char],
    chars: Chars,
    /// The last whitespace run measured by `space_end`.
    run: Range<usize>,
}

impl Scanner<'_> {
    /// Whether `literal` is at `index`.
    fn at(&self, index: usize, literal: &str) -> bool {
        let mut rest = self.text.get(index..).unwrap_or_default().iter();
        literal
            .chars()
            .all(|expected| rest.next() == Some(&expected))
    }

    /// The end of `\s*` from `start`.
    fn space_end(&mut self, start: usize) -> usize {
        if self.run.contains(&start) {
            return self.run.end;
        }
        let end = start + self.count(start, |c| self.chars.is_space(c));
        if end > start {
            self.run = start..end;
        }
        end
    }

    /// The number of characters from `start` that `accept` accepts.
    fn count(&self, start: usize, accept: impl Fn(char) -> bool) -> usize {
        self.text[start..]
            .iter()
            .take_while(|&&c| accept(c))
            .count()
    }

    /// The end of `[ \t]*` from `start`.
    fn blanks_end(&self, start: usize) -> usize {
        start + self.count(start, |c| c == ' ' || c == '\t')
    }

    /// The end of `[^{}]+` from `start`, if it matches.
    fn non_braces_end(&self, start: usize) -> Option<usize> {
        let count = self.count(start, |c| c != '{' && c != '}');
        (count > 0).then_some(start + count)
    }

    /// The end of `\r?\n` at `start`, if it matches.
    fn line_break_end(&self, start: usize) -> Option<usize> {
        if self.at(start, "\r\n") {
            Some(start + 2)
        } else if self.at(start, "\n") {
            Some(start + 1)
        } else {
            None
        }
    }

    /// The end of one `[ \t]*{{(...)}}[ \t]*` at `start`, if it matches.
    fn tag_end(&self, start: usize, tags: Tags) -> Option<usize> {
        let open = self.blanks_end(start);
        if !self.at(open, "{{") {
            return None;
        }
        let name = open + 2;
        let close = match self.text.get(name) {
            Some(sigil) if tags.sigils().contains(sigil) => self.non_braces_end(name + 1)?,
            // `else` is tried before `else if [^{}]+`.
            _ if matches!(tags, Tags::Line) && self.at(name, "else}}") => name + 4,
            _ if matches!(tags, Tags::Line) && self.at(name, "else if ") => {
                self.non_braces_end(name + 8)?
            }
            _ => return None,
        };
        self.at(close, "}}").then(|| self.blanks_end(close + 2))
    }

    /// The end of the longest `(...)+` of tags at `start`, if there is one.
    fn tags_end(&self, start: usize, tags: Tags) -> Option<usize> {
        let mut end = None;
        let mut position = start;
        while let Some(next) = self.tag_end(position, tags) {
            end = Some(next);
            position = next;
        }
        end
    }

    /// The end of the match of pybars' expression at `start`, if any: its
    /// alternatives in order.
    fn match_at(&mut self, start: usize) -> Option<usize> {
        // ~}}\s*
        if self.at(start, "~}}") {
            return Some(self.space_end(start + 3));
        }
        // \s*{{~
        let spaces = self.space_end(start);
        if self.at(spaces, "{{~") {
            return Some(spaces + 3);
        }
        // (?<=\n)(...)+\r?\n
        if start > 0 && self.text[start - 1] == '\n' {
            let end = self.tags_end(start, Tags::Line);
            if let Some(end) = end.and_then(|end| self.line_break_end(end)) {
                return Some(end);
            }
        }
        // ^(...)+\r?\n
        if start == 0 {
            let end = self.tags_end(start, Tags::FirstLine);
            if let Some(end) = end.and_then(|end| self.line_break_end(end)) {
                return Some(end);
            }
        }
        // \r?\n(...)+$, where `$` also matches before a final newline.
        let end = self
            .line_break_end(start)
            .and_then(|after| self.tags_end(after, Tags::LastLine))?;
        let len = self.text.len();
        (end == len || (end + 1 == len && self.text[end] == '\n')).then_some(end)
    }
}

/// `text.strip()`.
fn strip(text: &[char], chars: Chars) -> &[char] {
    let start = text.iter().take_while(|&&c| chars.is_space(c)).count();
    let end = text.len()
        - text[start..]
            .iter()
            .rev()
            .take_while(|&&c| chars.is_space(c))
            .count();
    &text[start..end]
}

/// Write `text` without the matches of `(?<={{)~|~(?=}})|(?<=}})[ \t]+(?={{)`.
fn clean_up(text: &[char], output: &mut Vec<char>) {
    let pair_at = |index: usize, pair: [char; 2]| text.get(index..index + 2) == Some(&pair[..]);
    let mut index = 0;
    while index < text.len() {
        let c = text[index];
        let after = |pair| index >= 2 && pair_at(index - 2, pair);
        if c == '~' && (after(['{', '{']) || pair_at(index + 1, ['}', '}'])) {
            index += 1;
            continue;
        }
        if (c == ' ' || c == '\t') && after(['}', '}']) {
            let end = index
                + text[index..]
                    .iter()
                    .take_while(|&&c| c == ' ' || c == '\t')
                    .count();
            if pair_at(end, ['{', '{']) {
                index = end;
                continue;
            }
        }
        output.push(c);
        index += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::UnicodeVersion;

    fn control(text: &str) -> String {
        let text: Vec<char> = text.chars().collect();
        whitespace_control(&text, Chars::new(UnicodeVersion::LATEST))
            .into_iter()
            .collect()
    }

    /// pybars3 0.9.7's `Compiler().whitespace_control(source)` for each
    /// source.
    #[test]
    fn matches_pybars() {
        for (source, expected) in [
            ("", ""),
            ("a {{b}} c", "a {{b}} c"),
            // ~}}\s* and \s*{{~
            ("{{a~}}  \n b", "{{a}}b"),
            ("a \t\n {{~b}}", "a{{b}}"),
            ("a {{~b~}} c", "a{{b}}c"),
            ("{{~~}}", "{{}}"),
            ("x\u{3000}{{~y}}", "x{{y}}"),
            // A line of block tags.
            ("x\n{{#if a}}\ny\n{{/if}}\nz", "x\n{{#if a}}y\n{{/if}}z"),
            ("x\n  {{#a}} {{#b}} \r\ny", "x\n{{#a}}{{#b}}y"),
            ("x\n{{else}}\n{{else if b}}\ny", "x\n{{else}}{{else if b}}y"),
            ("x\n{{else  if b}}\ny", "x\n{{else  if b}}\ny"),
            ("x\n{{elsewhere}}\ny", "x\n{{elsewhere}}\ny"),
            ("x\n{{^a}}\ny", "x\n{{^a}}\ny"),
            ("x\n{{#a\nb}}\ny", "x\n{{#a\nb}}y"),
            ("x\n{{#a~b}}\ny", "x\n{{#a~b}}y"),
            ("x\n{{#a{b}}\ny", "x\n{{#a{b}}\ny"),
            ("x\n{{#}}\ny", "x\n{{#}}\ny"),
            ("x\n{{else if }}\ny", "x\n{{else if }}\ny"),
            ("x\n{{#a}}y\n", "x\n{{#a}}y\n"),
            // The first line.
            ("  {{#a}}  \nb", "{{#a}}b"),
            ("{{/a}}\nb", "{{/a}}\nb"),
            // The last line, also before a final newline.
            ("a\n  {{/b}}  ", "a{{/b}}"),
            ("a\n{{/b}}\n", "a{{/b}}\n"),
            ("a\r\n{{/b}}\n", "a{{/b}}\n"),
            ("a\n{{#b}}", "a\n{{#b}}"),
            // Not the last line: a line of tags instead.
            ("a\n{{/b}}\r\n", "a\n{{/b}}"),
            ("a\n{{/b}}\n\n", "a\n{{/b}}\n"),
        ] {
            assert_eq!(control(source), expected, "{source:?}");
        }
    }

    /// `re.sub(r'(?<={{)~|~(?=}})|(?<=}})[ \t]+(?={{)', '', text)`.
    #[test]
    fn clean_up_matches_python() {
        for (text, expected) in [
            ("{{~a~}}", "{{a}}"),
            ("{{a~b}}", "{{a~b}}"),
            ("a~}}", "a}}"),
            ("{{~", "{{"),
            ("~", "~"),
            ("}} \t{{", "}}{{"),
            ("}} x", "}} x"),
        ] {
            let text: Vec<char> = text.chars().collect();
            let mut output = Vec::new();
            clean_up(&text, &mut output);
            assert_eq!(output.into_iter().collect::<String>(), expected);
        }
    }

    #[test]
    fn strip_uses_python_whitespace() {
        let chars = Chars::new(UnicodeVersion::LATEST);
        let text: Vec<char> = "\u{85}\x1c a \u{2028}".chars().collect();
        assert_eq!(strip(&text, chars), &['a']);
        assert_eq!(strip(&[' ', ' '], chars), &[] as &[char]);
    }
}
