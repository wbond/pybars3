//! pybars' `handlebars_grammar`, one method per rule, on the PyMeta
//! semantics of [`crate::runtime`]. pybars3 0.9.6 and 0.9.7 have the same
//! grammar.
//!
//! Each method's doc comment is the rule it implements. Every rule without
//! arguments goes through [`Parser::apply`], as PyMeta's `_apply` does;
//! `symbolfinish` and `rawblockfinish` take an argument and are not memoized.
//! Tag arguments, paths and literals are in [`args`].

mod args;

use args::argument_list;

use crate::chars::Chars;
use crate::runtime::{P, Parser, RuleId, Stop, rules::FIRST_GRAMMAR_RULE};
use crate::tree::{Arg, Block, Item};
use crate::{Fallback, Options};

macro_rules! rule_ids {
    ($($name:ident),* $(,)?) => {
        #[allow(non_camel_case_types, clippy::upper_case_acronyms, clippy::enum_variant_names)]
        #[derive(Clone, Copy)]
        #[repr(u32)]
        enum R { $($name),* }
        $(pub(super) const $name: RuleId = FIRST_GRAMMAR_RULE + R::$name as RuleId;)*
        // The failure memo keeps one bit per rule in a `u64`.
        const _: () = assert!(
            (FIRST_GRAMMAR_RULE as usize) + [$(R::$name),*].len() <= u64::BITS as usize,
            "more rules than bits in the failure memo",
        );
    };
}

rule_ids!(
    TEMPLATE,
    TEXT,
    NEWLINE_TEXT,
    WHITESPACE_TEXT,
    OTHER_TEXT,
    TEMPLATECOMMAND,
    START,
    FINISH,
    COMMENT,
    SPACE,
    ARGUMENTS,
    SUBEXPRESSION,
    EXPRESSION_INNER,
    EXPRESSION,
    ESCAPEDEXPRESSION,
    BLOCK_INNER,
    PARTIAL_INNER,
    ALT_INNER,
    PARTIAL,
    PATH,
    KWLITERAL,
    LITERAL,
    STRING,
    INTEGER,
    BOOLEAN,
    FALSE,
    TRUE,
    NULL,
    UNDEFINED,
    NOTDQUOTE,
    NOTSQUOTE,
    ESCAPEDQUOTE,
    NOTCLOSEBRACKET,
    SAFESYMBOL,
    SYMBOL,
    PARTIALNAME,
    PATHSEG,
    BLOCKRULE,
    ALTTEMPLATE,
    RAWBLOCKSTART,
    RAWBLOCK,
);

/// What the `template` rule returned: the tree, and PyMeta's error position.
pub(crate) struct Parsed {
    pub(crate) tree: Vec<Item>,
    pub(crate) error_position: usize,
}

/// Apply `template` to `text`, as `Compiler._handlebars(text).apply('template')`.
pub(crate) fn parse(text: &[char], chars: Chars, options: &Options) -> Result<Parsed, Fallback> {
    let mut parser = Parser::new(text, chars, options);
    match parser.template() {
        Ok(tree) => Ok(Parsed {
            tree,
            error_position: parser.current_error,
        }),
        Err(Stop::Fallback(fallback)) => Err(fallback),
        // `template` is `(...)*`, which cannot fail.
        Err(Stop::Fail(_)) => unreachable!("the template rule failed"),
    }
}

impl Parser<'_> {
    /// A template or subexpression, one level deeper.
    fn nested<T>(&mut self, body: impl FnOnce(&mut Self) -> P<T>) -> P<T> {
        if self.depth >= self.nesting_limit {
            return Err(Stop::Fallback(Fallback::NestingDepth));
        }
        self.depth += 1;
        let result = body(self);
        self.depth -= 1;
        result
    }

    /// `template ::= (<text> | <templatecommand>)*:body => ['template'] + body`
    fn template(&mut self) -> P<Vec<Item>> {
        self.apply(TEMPLATE, |p| {
            p.nested(|p| {
                let mut body = vec![Item::Marker];
                body.extend(p.many(|p| p.choice(&[Parser::text, Parser::templatecommand]))?);
                Ok(body)
            })
        })
    }

    /// `text ::= <newline_text> | <whitespace_text> | <other_text>`
    fn text(&mut self) -> P<Item> {
        self.apply(TEXT, |p| {
            p.choice(&[
                Parser::newline_text,
                Parser::whitespace_text,
                Parser::other_text,
            ])
        })
    }

    /// `newline_text ::= (~(<start>) ('\r'?'\n'):char) => ('newline', u'' + char)`
    fn newline_text(&mut self) -> P<Item> {
        self.apply(NEWLINE_TEXT, |p| {
            p.not(Parser::start)?;
            p.optional(|p| p.exactly('\r'))?;
            let c = p.exactly('\n')?;
            Ok(Item::Newline(c.to_string()))
        })
    }

    /// `whitespace_text ::= (~(<start>) (' '|'\t'))+:text => ('whitespace', u''.join(text))`
    fn whitespace_text(&mut self) -> P<Item> {
        self.apply(WHITESPACE_TEXT, |p| {
            let text = p.many1_string(|p| {
                p.not(Parser::start)?;
                p.choice(&[|p| p.exactly(' '), |p| p.exactly('\t')])
            })?;
            Ok(Item::Whitespace(text))
        })
    }

    /// `other_text ::= (~(<start>) <anything>)+:text => ('literal', u''.join(text))`
    ///
    /// The repetition runs to the next `{{` (or the end) in one step: every
    /// iteration before it consumes its character, considers its position
    /// and leaves `start`'s failure marker there. The iteration that stops
    /// the run is applied as PyMeta would: at a `{{`, `start` matches (its two
    /// characters are considered); at the end, `start` and `anything` fail.
    fn other_text(&mut self) -> P<Item> {
        self.apply(OTHER_TEXT, |p| {
            let start = p.pos;
            let stop = p.next_start(start);
            if stop == start {
                // `+` fails on its first iteration.
                p.not(Parser::start)?;
                p.anything()?;
                unreachable!("start matches here, or the text ended");
            }
            for position in start..stop {
                p.mark_failed(START, position);
            }
            p.consider(Some(stop - 1));
            p.pos = stop;
            // The iteration that ends the repetition.
            let _ = p.not(Parser::start).and_then(|()| p.anything());
            p.pos = stop;
            Ok(Item::Literal(p.text[start..stop].iter().collect()))
        })
    }

    /// `templatecommand ::= <blockrule> | <comment> | <escapedexpression> | <expression> | <partial> | <rawblock>`
    fn templatecommand(&mut self) -> P<Item> {
        self.apply(TEMPLATECOMMAND, |p| {
            p.choice(&[
                Parser::blockrule,
                Parser::comment,
                Parser::escapedexpression,
                Parser::expression,
                Parser::partial,
                Parser::rawblock,
            ])
        })
    }

    /// `start ::= '{' '{'`
    fn start(&mut self) -> P<()> {
        self.apply(START, |p| p.exactly_str("{{"))
    }

    /// `finish ::= '}' '}'`
    fn finish(&mut self) -> P<()> {
        self.apply(FINISH, |p| p.exactly_str("}}"))
    }

    /// `comment ::= <start> '!' (~(<finish>) <anything>)* <finish> => ('comment', )`
    fn comment(&mut self) -> P<Item> {
        self.apply(COMMENT, |p| {
            p.start()?;
            p.exactly('!')?;
            p.many(|p| {
                p.not(Parser::finish)?;
                p.anything()
            })?;
            p.finish()?;
            Ok(Item::Comment)
        })
    }

    /// `space ::= ' '|'\t'|'\r'|'\n'`
    fn space(&mut self) -> P<char> {
        self.apply(SPACE, |p| {
            p.choice(&[
                |p| p.exactly(' '),
                |p| p.exactly('\t'),
                |p| p.exactly('\r'),
                |p| p.exactly('\n'),
            ])
        })
    }

    /// `arguments ::= (<space>+ (<kwliteral>|<literal>|<path>|<subexpression>))*:arguments => arguments`
    fn arguments(&mut self) -> P<Vec<Arg>> {
        self.apply(ARGUMENTS, argument_list)
    }

    /// `subexpression ::= '(' <spaces> <path>:p (<space>+ (...))*:arguments <spaces> ')' => ('subexpr', p, arguments)`
    fn subexpression(&mut self) -> P<Arg> {
        self.apply(SUBEXPRESSION, |p| {
            p.nested(|p| {
                p.exactly('(')?;
                p.spaces()?;
                let Arg::Path(segments) = p.path()? else {
                    unreachable!("path returns a path")
                };
                let arguments = argument_list(p)?;
                p.spaces()?;
                p.exactly(')')?;
                Ok(Arg::Subexpr(segments, arguments))
            })
        })
    }

    /// `expression_inner ::= <spaces> <path>:p <arguments>:arguments <spaces> <finish> => (p, arguments)`
    fn expression_inner(&mut self) -> P<(Vec<String>, Vec<Arg>)> {
        self.apply(EXPRESSION_INNER, |p| {
            p.spaces()?;
            let Arg::Path(segments) = p.path()? else {
                unreachable!("path returns a path")
            };
            let arguments = p.arguments()?;
            p.spaces()?;
            p.finish()?;
            Ok((segments, arguments))
        })
    }

    /// `expression ::= <start> '{' <expression_inner>:e '}' => ('expand', ) + e | <start> '&' <expression_inner>:e => ('expand', ) + e`
    fn expression(&mut self) -> P<Item> {
        self.apply(EXPRESSION, |p| {
            p.choice(&[
                |p| {
                    p.start()?;
                    p.exactly('{')?;
                    let (path, arguments) = p.expression_inner()?;
                    p.exactly('}')?;
                    Ok(Item::Expand(path, arguments))
                },
                |p| {
                    p.start()?;
                    p.exactly('&')?;
                    let (path, arguments) = p.expression_inner()?;
                    Ok(Item::Expand(path, arguments))
                },
            ])
        })
    }

    /// `escapedexpression ::= <start> <expression_inner>:e => ('escapedexpand', ) + e`
    fn escapedexpression(&mut self) -> P<Item> {
        self.apply(ESCAPEDEXPRESSION, |p| {
            p.start()?;
            let (path, arguments) = p.expression_inner()?;
            Ok(Item::EscapedExpand(path, arguments))
        })
    }

    /// `block_inner ::= <spaces> <symbol>:s <arguments>:args <spaces> <finish> => (u''.join(s), args)`
    fn block_inner(&mut self) -> P<(String, Vec<Arg>)> {
        self.apply(BLOCK_INNER, |p| {
            p.spaces()?;
            let symbol = p.symbol()?;
            let arguments = p.arguments()?;
            p.spaces()?;
            p.finish()?;
            Ok((symbol, arguments))
        })
    }

    /// `partial_inner ::= <spaces> <partialname>:s <arguments>:args <spaces> <finish> => (s, args)`
    fn partial_inner(&mut self) -> P<(Arg, Vec<Arg>)> {
        self.apply(PARTIAL_INNER, |p| {
            p.spaces()?;
            let name = p.partialname()?;
            let arguments = p.arguments()?;
            p.spaces()?;
            p.finish()?;
            Ok((name, arguments))
        })
    }

    /// `alt_inner ::= <spaces> ('^' | 'e' 'l' 's' 'e') <spaces> <finish>`
    fn alt_inner(&mut self) -> P<()> {
        self.apply(ALT_INNER, |p| {
            p.spaces()?;
            p.choice(&[|p| p.exactly('^').map(drop), |p| p.exactly_str("else")])?;
            p.spaces()?;
            p.finish()
        })
    }

    /// `partial ::= <start> '>' <partial_inner>:i => ('partial',) + i`
    fn partial(&mut self) -> P<Item> {
        self.apply(PARTIAL, |p| {
            p.start()?;
            p.exactly('>')?;
            let (name, arguments) = p.partial_inner()?;
            Ok(Item::Partial(name, arguments))
        })
    }

    /// `symbolfinish :expected ::= <start> '/' <symbol>:found ?(found == expected) <finish>`
    fn symbolfinish(&mut self, expected: &str) -> P<()> {
        self.take_argument();
        self.start()?;
        self.exactly('/')?;
        let found = self.symbol()?;
        self.pred(found == expected)?;
        self.finish()
    }

    /// `blockrule ::= <start> '#' <block_inner>:i <template>:t <alttemplate>:alt_t <symbolfinish i[0]> => ('block',) + i + (t, alt_t) | <start> '^' ... => ('invertedblock',) + ...`
    fn blockrule(&mut self) -> P<Item> {
        self.apply(BLOCKRULE, |p| {
            p.choice(&[|p| p.block('#'), |p| p.block('^')])
        })
    }

    fn block(&mut self, opener: char) -> P<Item> {
        self.start()?;
        self.exactly(opener)?;
        let (symbol, args) = self.block_inner()?;
        let body = self.template()?;
        let alt = self.alttemplate()?;
        self.symbolfinish(&symbol)?;
        Ok(Item::Block(Box::new(Block {
            inverted: opener == '^',
            symbol,
            args,
            body,
            alt,
        })))
    }

    /// `alttemplate ::= (<start> <alt_inner> <template>)?:alt_t => alt_t or []`
    fn alttemplate(&mut self) -> P<Vec<Item>> {
        self.apply(ALTTEMPLATE, |p| {
            let alt = p.optional(|p| {
                p.start()?;
                p.alt_inner()?;
                p.template()
            })?;
            Ok(alt.unwrap_or_default())
        })
    }

    /// `rawblockstart ::= <start> <start> <block_inner>:i <finish> => i`
    fn rawblockstart(&mut self) -> P<(String, Vec<Arg>)> {
        self.apply(RAWBLOCKSTART, |p| {
            p.start()?;
            p.start()?;
            let inner = p.block_inner()?;
            p.finish()?;
            Ok(inner)
        })
    }

    /// `rawblockfinish :expected ::= <start> <symbolfinish expected> <finish>`
    fn rawblockfinish(&mut self, expected: &str) -> P<()> {
        self.take_argument();
        self.start()?;
        self.symbolfinish(expected)?;
        self.finish()
    }

    /// `rawblock ::= <rawblockstart>:i (~(<rawblockfinish i[0]>) <anything>)*:r <rawblockfinish i[0]> => ('rawblock',) + i + (''.join(r),)`
    fn rawblock(&mut self) -> P<Item> {
        self.apply(RAWBLOCK, |p| {
            let (symbol, args) = p.rawblockstart()?;
            let raw: String = p
                .many(|p| {
                    p.not(|p| p.rawblockfinish(&symbol))?;
                    p.anything()
                })?
                .into_iter()
                .collect();
            p.rawblockfinish(&symbol)?;
            Ok(Item::RawBlock(symbol, args, raw))
        })
    }
}
