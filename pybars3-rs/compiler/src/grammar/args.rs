//! The rules for tag arguments: paths, keyword arguments and literals.

use super::{
    BOOLEAN, ESCAPEDQUOTE, FALSE, INTEGER, KWLITERAL, LITERAL, NOTCLOSEBRACKET, NOTDQUOTE,
    NOTSQUOTE, NULL, PARTIALNAME, PATH, PATHSEG, SAFESYMBOL, STRING, SYMBOL, TRUE, UNDEFINED,
};
use crate::Fallback;
use crate::pyrepr;
use crate::runtime::{P, Parser, Stop};
use crate::tree::Arg;

/// `arguments` and `subexpression` arguments: `(<space>+ (<kwliteral>|<literal>|<path>|<subexpression>))*`.
pub(super) fn argument_list(p: &mut Parser<'_>) -> P<Vec<Arg>> {
    p.many(|p| {
        p.many1(Parser::space)?;
        p.choice(&[
            Parser::kwliteral,
            Parser::literal,
            Parser::path,
            Parser::subexpression,
        ])
    })
}

impl Parser<'_> {
    /// `path ::= ~('/') <pathseg>+:segments => ('path', segments)`
    pub(super) fn path(&mut self) -> P<Arg> {
        self.apply(PATH, |p| {
            p.not(|p| p.exactly('/'))?;
            Ok(Arg::Path(p.many1(Parser::pathseg)?))
        })
    }

    /// `kwliteral ::= <safesymbol>:s '=' (<literal>|<path>|<subexpression>):v => ('kwparam', s, v)`
    fn kwliteral(&mut self) -> P<Arg> {
        self.apply(KWLITERAL, |p| {
            let name = p.safesymbol()?;
            p.exactly('=')?;
            let value = p.choice(&[Parser::literal, Parser::path, Parser::subexpression])?;
            Ok(Arg::Keyword(name, Box::new(value)))
        })
    }

    /// `literal ::= (<string>|<integer>|<boolean>|<null>|<undefined>):thing => ('literalparam', thing)`
    fn literal(&mut self) -> P<Arg> {
        self.apply(LITERAL, |p| {
            p.choice(&[
                Parser::string,
                Parser::integer,
                Parser::boolean,
                Parser::null,
                Parser::undefined,
            ])
            .map(Arg::Literal)
        })
    }

    /// `string ::= '"' <notdquote>*:ls '"' => u'"' + u''.join(ls) + u'"' | "'" <notsquote>*:ls "'" => ...`
    fn string(&mut self) -> P<String> {
        self.apply(STRING, |p| {
            p.choice(&[
                |p| p.quoted('"', Parser::notdquote),
                |p| p.quoted('\'', Parser::notsquote),
            ])
        })
    }

    fn quoted(&mut self, quote: char, piece: fn(&mut Self) -> P<String>) -> P<String> {
        self.exactly(quote)?;
        let pieces = self.many(piece)?;
        self.exactly(quote)?;
        let mut text = String::from(quote);
        text.extend(pieces);
        text.push(quote);
        Ok(text)
    }

    /// `integer ::= '-'?:sign <digit>+:ds => int((sign if sign else '') + ''.join(ds))`
    fn integer(&mut self) -> P<String> {
        self.apply(INTEGER, |p| {
            let sign = p.optional(|p| p.exactly('-'))?;
            let digits = p.many1_string(Parser::digit)?;
            let text = format!("{}{digits}", if sign.is_some() { "-" } else { "" });
            pyrepr::int_str(&text, p.chars, p.int_max_str_digits)
                .map_err(|_| Stop::Fallback(Fallback::IntConversion))
        })
    }

    /// `boolean ::= <false>|<true>`
    fn boolean(&mut self) -> P<String> {
        self.apply(BOOLEAN, |p| p.choice(&[Parser::false_, Parser::true_]))
    }

    /// `false ::= 'f' 'a' 'l' 's' 'e' => False`
    fn false_(&mut self) -> P<String> {
        self.apply(FALSE, |p| {
            p.exactly_str("false").map(|()| "False".to_owned())
        })
    }

    /// `true ::= 't' 'r' 'u' 'e' => True`
    fn true_(&mut self) -> P<String> {
        self.apply(TRUE, |p| p.exactly_str("true").map(|()| "True".to_owned()))
    }

    /// `null ::= ('n' 'u' 'l' 'l') => None`
    fn null(&mut self) -> P<String> {
        self.apply(NULL, |p| p.exactly_str("null").map(|()| "None".to_owned()))
    }

    /// `undefined ::= ('u' 'n' 'd' 'e' 'f' 'i' 'n' 'e' 'd') => None`
    fn undefined(&mut self) -> P<String> {
        self.apply(UNDEFINED, |p| {
            p.exactly_str("undefined").map(|()| "None".to_owned())
        })
    }

    /// `notdquote ::= <escapedquote> | '\n' => '\\n' | '\r' => '\\r' | '\\' => '\\\\' | (~('"') <anything>)`
    fn notdquote(&mut self) -> P<String> {
        self.apply(NOTDQUOTE, |p| p.string_piece('"'))
    }

    /// `notsquote ::= <escapedquote> | '\n' => '\\n' | '\r' => '\\r' | '\\' => '\\\\' | (~("'") <anything>)`
    fn notsquote(&mut self) -> P<String> {
        self.apply(NOTSQUOTE, |p| p.string_piece('\''))
    }

    fn string_piece(&mut self, quote: char) -> P<String> {
        let other: fn(&mut Self) -> P<String> = if quote == '"' {
            |p| {
                p.not(|p| p.exactly('"'))?;
                p.anything().map(String::from)
            }
        } else {
            |p| {
                p.not(|p| p.exactly('\''))?;
                p.anything().map(String::from)
            }
        };
        self.choice(&[
            Parser::escapedquote,
            |p| p.exactly('\n').map(|_| "\\n".to_owned()),
            |p| p.exactly('\r').map(|_| "\\r".to_owned()),
            |p| p.exactly('\\').map(|_| "\\\\".to_owned()),
            other,
        ])
    }

    /// `escapedquote ::= '\\' '"' => '\\"' | "\\" "'" => "\\'"`
    fn escapedquote(&mut self) -> P<String> {
        self.apply(ESCAPEDQUOTE, |p| {
            p.choice(&[
                |p| p.exactly_str("\\\"").map(|()| "\\\"".to_owned()),
                |p| p.exactly_str("\\'").map(|()| "\\'".to_owned()),
            ])
        })
    }

    /// `notclosebracket ::= (~(']') <anything>)`
    fn notclosebracket(&mut self) -> P<char> {
        self.apply(NOTCLOSEBRACKET, |p| {
            p.not(|p| p.exactly(']'))?;
            p.anything()
        })
    }

    /// `<notclosebracket>+`, in one step: what running the rule at every
    /// position up to the next `]` does, without rescanning the same text
    /// for every `[` (pybars is quadratic on `{{x.[a[a[a...`).
    ///
    /// Before the `]` (or the end) every application succeeds and considers
    /// its position. At the `]` or the end, the application that ends the
    /// loop fails, unless its marker is already there, after considering the
    /// `]` (`exactly` succeeded inside `~`) or the end (`~` succeeded), and
    /// leaves its markers; at the end `anything` fails too.
    ///
    /// Returns the range of the characters matched; the caller builds the
    /// string only when the closing `]` follows.
    fn notclosebrackets(&mut self) -> P<std::ops::Range<usize>> {
        let start = self.pos;
        let stop = self.next_close_bracket(start);
        // The first application, which `+` requires to succeed.
        if stop == start || self.has_failed(NOTCLOSEBRACKET, start) {
            self.many1(Parser::notclosebracket)?;
            return Ok(start..self.pos);
        }
        self.consider(Some(stop - 1));
        self.pos = stop;
        if !self.has_failed(NOTCLOSEBRACKET, stop) {
            self.consider(Some(stop));
            if stop == self.text.len() {
                self.mark_failed(crate::runtime::rules::ANYTHING, stop);
            }
            self.mark_failed(NOTCLOSEBRACKET, stop);
        }
        Ok(start..stop)
    }

    /// `safesymbol ::= ~<alt_inner> '['? (<letter>|'_'):start (<letterOrDigit>|'_')+:symbol ']'? => start + u''.join(symbol)`
    fn safesymbol(&mut self) -> P<String> {
        self.apply(SAFESYMBOL, |p| {
            p.not(Parser::alt_inner)?;
            p.optional(|p| p.exactly('['))?;
            let first = p.choice(&[Parser::letter, |p| p.exactly('_')])?;
            let rest =
                p.many1_string(|p| p.choice(&[Parser::letter_or_digit, |p| p.exactly('_')]))?;
            p.optional(|p| p.exactly(']'))?;
            Ok(format!("{first}{rest}"))
        })
    }

    /// `symbol ::= ~<alt_inner> '['? (<letterOrDigit>|'-'|'@')+:symbol ']'? => u''.join(symbol)`
    pub(super) fn symbol(&mut self) -> P<String> {
        self.apply(SYMBOL, |p| {
            p.not(Parser::alt_inner)?;
            p.optional(|p| p.exactly('['))?;
            let symbol = p.many1_string(|p| {
                p.choice(&[
                    Parser::letter_or_digit,
                    |p| p.exactly('-'),
                    |p| p.exactly('@'),
                ])
            })?;
            p.optional(|p| p.exactly(']'))?;
            Ok(symbol)
        })
    }

    /// `partialname ::= <subexpression>:s => s | ~<alt_inner> ('['|'"')? (~(<space>|<finish>|']'|'"' ) <anything>)+:symbol (']'|'"')? => ('literalparam', '"' + u''.join(symbol) + '"')`
    pub(super) fn partialname(&mut self) -> P<Arg> {
        self.apply(PARTIALNAME, |p| {
            p.choice(&[Parser::subexpression, |p| {
                p.not(Parser::alt_inner)?;
                p.optional(|p| p.choice(&[|p| p.exactly('['), |p| p.exactly('"')]))?;
                let name = p.many1_string(|p| {
                    p.not(|p| {
                        p.choice(&[
                            |p| p.space().map(drop),
                            Parser::finish,
                            |p| p.exactly(']').map(drop),
                            |p| p.exactly('"').map(drop),
                        ])
                    })?;
                    p.anything()
                })?;
                p.optional(|p| p.choice(&[|p| p.exactly(']'), |p| p.exactly('"')]))?;
                Ok(Arg::Literal(format!("\"{name}\"")))
            }])
        })
    }

    /// `pathseg ::= '[' <notclosebracket>+:symbol ']' => u''.join(symbol) | ('@' '.' '.' '/') => u'@@_parent' | <symbol> | '/' => u'' | ('.' '.' '/') => u'@_parent' | '.' => u''`
    fn pathseg(&mut self) -> P<String> {
        self.apply(PATHSEG, |p| {
            p.choice(&[
                |p| {
                    p.exactly('[')?;
                    let symbol = p.notclosebrackets()?;
                    p.exactly(']')?;
                    Ok(p.text[symbol].iter().collect())
                },
                |p| p.exactly_str("@../").map(|()| "@@_parent".to_owned()),
                Parser::symbol,
                |p| p.exactly('/').map(|_| String::new()),
                |p| p.exactly_str("../").map(|()| "@_parent".to_owned()),
                |p| p.exactly('.').map(|_| String::new()),
            ])
        })
    }
}
