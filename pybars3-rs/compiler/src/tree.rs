//! The tree that pybars' `handlebars_grammar` builds, as typed Rust values.
//!
//! A template is pybars' list `['template', item, ...]`: [`Item::Marker`]
//! stands for the leading `'template'` string, so that list indices match
//! pybars' and [`crate::whitespace`] can follow its index arithmetic exactly.

/// One element of a template list.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Item {
    /// The `'template'` string that starts every template list.
    Marker,
    /// `('literal', text)`.
    Literal(String),
    /// `('newline', '\n')`.
    Newline(String),
    /// `('whitespace', text)`.
    Whitespace(String),
    /// `('comment',)`.
    Comment,
    /// `('expand', path, arguments)`: `{{{x}}}` and `{{&x}}`.
    Expand(Vec<String>, Vec<Arg>),
    /// `('escapedexpand', path, arguments)`: `{{x}}`.
    EscapedExpand(Vec<String>, Vec<Arg>),
    /// `('block', symbol, arguments, template, alt)` or `('invertedblock', ...)`.
    Block(Box<Block>),
    /// `('partial', name, arguments)`; the name is a subexpression or a
    /// quoted literal.
    Partial(Arg, Vec<Arg>),
    /// `('rawblock', symbol, arguments, raw)`.
    RawBlock(String, Vec<Arg>, String),
}

/// A `{{#symbol}}` or `{{^symbol}}` block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Block {
    /// `true` for `{{^symbol}}`.
    pub(crate) inverted: bool,
    pub(crate) symbol: String,
    pub(crate) args: Vec<Arg>,
    /// The block's template list.
    pub(crate) body: Vec<Item>,
    /// The `{{else}}` template list, or pybars' `[]`.
    pub(crate) alt: Vec<Item>,
}

/// The first element of each tuple, which pybars' `clean_whitespace` tests.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Tag {
    /// `'template'[0]`, the character `'t'`.
    T,
    Literal,
    Newline,
    Whitespace,
    Comment,
    Expand,
    EscapedExpand,
    Block,
    InvertedBlock,
    Partial,
    RawBlock,
}

impl Item {
    /// `item[0]`.
    pub(crate) fn tag(&self) -> Tag {
        match self {
            Item::Marker => Tag::T,
            Item::Literal(_) => Tag::Literal,
            Item::Newline(_) => Tag::Newline,
            Item::Whitespace(_) => Tag::Whitespace,
            Item::Comment => Tag::Comment,
            Item::Expand(..) => Tag::Expand,
            Item::EscapedExpand(..) => Tag::EscapedExpand,
            Item::Block(block) if block.inverted => Tag::InvertedBlock,
            Item::Block(_) => Tag::Block,
            Item::Partial(..) => Tag::Partial,
            Item::RawBlock(..) => Tag::RawBlock,
        }
    }
}

/// An argument of a tag.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Arg {
    /// `('kwparam', name, value)`.
    Keyword(String, Box<Arg>),
    /// `('literalparam', value)`, with the value as `str()` prints it.
    Literal(String),
    /// `('path', segments)`.
    Path(Vec<String>),
    /// `('subexpr', ('path', segments), arguments)`.
    Subexpr(Vec<String>, Vec<Arg>),
}
