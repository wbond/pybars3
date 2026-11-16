//! pybars' `compile_grammar` and `CodeBuilder`: turn the cleaned tree into
//! the Python source that `Compiler.precompile` returns.
//!
//! The grammar walks the tree in order and calls the builder; nested
//! templates become `block_N` functions numbered in the order the walk
//! starts them, and each function's code is preceded by the code of the
//! functions it references. The text written for each item is pybars'
//! byte for byte, including its lack of escaping of path segments.

use std::fmt::Write as _;

use crate::PybarsVersion;
use crate::chars::Chars;
use crate::pyrepr::{repr_into, repr_str};
use crate::tree::{Arg, Block, Item};

/// The header of `FunctionContainer.full_code`, which writes
/// `pybars.__version__` into it twice.
macro_rules! header {
    ($version:literal) => {
        concat!(
            "import pybars\n",
            "\n",
            "if pybars.__version__ != '",
            $version,
            "':\n",
            "    raise pybars.PybarsError(\"This template was precompiled with pybars3 version ",
            $version,
            ", running version %s\" % pybars.__version__)\n",
            "\n",
            "from pybars import strlist, Scope, PybarsError\n",
            "from pybars._compiler import _pybars_, escape, resolve, resolve_subexpr, prepare, ensure_scope\n",
            "\n",
            "from functools import partial\n",
            "\n",
            "\n",
        )
    };
}

/// The header of the modules generated for `version`.
pub(crate) const fn header(version: PybarsVersion) -> &'static str {
    match version {
        PybarsVersion::V0_9_6 => header!("0.9.6"),
        PybarsVersion::V0_9_7 => header!("0.9.7"),
    }
}

const RENDER_PROLOGUE: &str = "def render(context, helpers=None, partials=None, root=None):\n    \
_helpers = dict(_pybars_['helpers'])\n    \
if helpers is not None:\n        \
_helpers.update(helpers)\n    \
helpers = _helpers\n    \
if partials is None:\n        \
partials = {}\n    \
called = root is None\n    \
if called:\n        \
root = context\n";

/// pybars raises `PybarsError` for a partial with two positional arguments.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ExtraPositionalArgument;

/// A generated function: pybars' `FunctionContainer`.
struct Function {
    name: String,
    code: String,
}

/// A function being written: one entry of `CodeBuilder.stack`.
struct Frame {
    name: String,
    lines: String,
    nested: Vec<Function>,
}

/// pybars' `CodeBuilder`, writing into `String`s.
struct Builder {
    stack: Vec<Frame>,
    render_counter: usize,
    chars: Chars,
}

/// `Compiler._generate_code(source).full_code` for a cleaned tree.
pub(crate) fn full_code(
    tree: &[Item],
    chars: Chars,
    version: PybarsVersion,
) -> Result<String, ExtraPositionalArgument> {
    let mut builder = Builder {
        stack: Vec::new(),
        render_counter: 0,
        chars,
    };
    let function = builder.compile(tree)?;
    Ok(format!("{}{}", header(version), function.code))
}

/// `pathseg` of the compile grammar, for one segment of an expand's path.
fn compiled_segment(segment: &str) -> &str {
    match segment {
        "/" | "." | "" | "this" => "",
        _ => segment,
    }
}

fn resolve_call(segments: &[String]) -> String {
    let segments: Vec<&str> = segments.iter().map(|s| compiled_segment(s)).collect();
    format!("resolve(context, u'{}')", segments.join("', u'"))
}

/// `complexarg` of the compile grammar.
fn complex_arg(arg: &Arg) -> String {
    match arg {
        Arg::Path(segments) => resolve_call(segments),
        Arg::Subexpr(segments, arguments) => {
            // `["path" <pathseg>:name]` hands pathseg the whole segment list,
            // whose `u''.join` concatenates the segments.
            let name = segments.concat();
            let mut call = format!("resolve_subexpr(helpers, \"{name}\", context");
            if !arguments.is_empty() {
                call.push_str(", ");
                call.push_str(
                    &arguments
                        .iter()
                        .map(arg_code)
                        .collect::<Vec<_>>()
                        .join(", "),
                );
            }
            call.push(')');
            call
        }
        Arg::Literal(value) => value.clone(),
        Arg::Keyword(..) => unreachable!("a keyword argument is not a complexarg"),
    }
}

/// `arg` of the compile grammar.
fn arg_code(arg: &Arg) -> String {
    match arg {
        Arg::Keyword(name, value) => format!("{name}={}", complex_arg(value)),
        _ => complex_arg(arg),
    }
}

/// `CodeBuilder.arguments_to_call`.
fn arguments_to_call(arguments: &[String]) -> String {
    let params: Vec<&str> = arguments
        .iter()
        .map(|a| if a.is_empty() { "context" } else { a.as_str() })
        .collect();
    if params.is_empty() {
        ")".to_owned()
    } else {
        format!(", {})", params.join(", "))
    }
}

fn wrap_nested(name: &str) -> String {
    format!("partial({name}, helpers=helpers, partials=partials, root=root)")
}

/// `re.match('(\w+)=(.+)$', argument)`: the keyword and its value.
fn keyword_match(argument: &str, chars: Chars) -> Option<(&str, &str)> {
    let word_end = argument
        .char_indices()
        .find(|&(_, c)| !chars.is_word(c))
        .map_or(argument.len(), |(i, _)| i);
    if word_end == 0 || !argument[word_end..].starts_with('=') {
        return None;
    }
    let rest = &argument[word_end + 1..];
    let line_end = rest.find('\n').unwrap_or(rest.len());
    let tail = &rest[line_end..];
    (line_end > 0 && (tail.is_empty() || tail == "\n"))
        .then(|| (&argument[..word_end], &rest[..line_end]))
}

impl Builder {
    fn top(&mut self) -> &mut Frame {
        self.stack.last_mut().expect("a function is being written")
    }

    fn grow(&mut self, text: &str) {
        self.top().lines.push_str(text);
    }

    /// `compile ::= <prolog> <rule>* => builder.finish()` over a template list.
    fn compile(&mut self, tree: &[Item]) -> Result<Function, ExtraPositionalArgument> {
        self.start();
        for item in &tree[1..] {
            self.rule(item)?;
        }
        Ok(self.finish())
    }

    fn start(&mut self) {
        let name = if self.render_counter == 0 {
            "render".to_owned()
        } else {
            format!("block_{}", self.render_counter)
        };
        self.render_counter += 1;
        let mut lines = if self.stack.is_empty() {
            RENDER_PROLOGUE.to_owned()
        } else {
            format!("def {name}(context, helpers, partials, root):\n")
        };
        lines.push_str("    result = strlist()\n    context = ensure_scope(context, root)\n");
        self.stack.push(Frame {
            name,
            lines,
            nested: Vec::new(),
        });
    }

    fn finish(&mut self) -> Function {
        let mut frame = self.stack.pop().expect("start precedes finish");
        if self.stack.is_empty() {
            frame
                .lines
                .push_str("    if called:\n        result = str(result)\n");
        }
        frame.lines.push_str("    return result\n");
        let mut code = String::new();
        for function in &frame.nested {
            code.push_str(&function.code);
            code.push('\n');
        }
        code.push_str(&frame.lines);
        Function {
            name: frame.name,
            code,
        }
    }

    fn rule(&mut self, item: &Item) -> Result<(), ExtraPositionalArgument> {
        match item {
            Item::Marker => unreachable!("the marker only starts a list"),
            Item::Literal(text) | Item::Newline(text) | Item::Whitespace(text) => {
                let chars = self.chars;
                let lines = &mut self.top().lines;
                lines.push_str("    result.append(");
                repr_into(lines, text, chars);
                lines.push_str(")\n");
            }
            Item::Comment => {}
            Item::Expand(path, arguments) => self.expand(path, arguments, "False"),
            Item::EscapedExpand(path, arguments) => self.expand(path, arguments, "True"),
            Item::Block(block) => self.block(block)?,
            Item::RawBlock(symbol, arguments, raw) => self.raw_block(symbol, arguments, raw),
            Item::Partial(name, arguments) => self.partial(name, arguments)?,
        }
        Ok(())
    }

    /// `add_expand` / `add_escaped_expand`, with `find_lookup`.
    fn expand(&mut self, segments: &[String], arguments: &[Arg], escape: &str) {
        let arguments: Vec<String> = arguments.iter().map(arg_code).collect();
        let call = arguments_to_call(&arguments);
        let lines = &mut self.top().lines;
        // Writing to a String cannot fail.
        let realname = if let [segment] = segments {
            let path = compiled_segment(segment);
            let realname = path.replace(".get(\"", "").replace("\")", "");
            let _ = write!(
                lines,
                "    value = helpers.get(u'{realname}')\n    if value is None:\n        value = resolve(context, u'{path}')\n"
            );
            realname
        } else {
            let _ = writeln!(lines, "    value = {}", resolve_call(segments));
            String::new()
        };
        let _ = write!(
            lines,
            "    if hasattr(value, '__call__'):\n        value = value(context{call}\n"
        );
        if !realname.is_empty() {
            let _ = write!(
                lines,
                "    elif value is None:\n        value = helpers['helperMissing'](context, u'{realname}'{call}\n"
            );
        }
        let _ = writeln!(lines, "    result.grow(prepare(value, {escape}))");
    }

    /// `add_block` / `add_invertedblock`.
    fn block(&mut self, block: &Block) -> Result<(), ExtraPositionalArgument> {
        let arguments: Vec<String> = block.args.iter().map(arg_code).collect();
        let nested = self.compile(&block.body)?;
        let alt = if block.alt.is_empty() {
            None
        } else {
            Some(self.compile(&block.alt)?)
        };
        let (main_key, alt_key) = if block.inverted {
            ("inverse", "fn")
        } else {
            ("fn", "inverse")
        };
        let name = nested.name.clone();
        let alt_name = alt.as_ref().map(|f| f.name.clone());
        let frame = self.top();
        frame.nested.push(nested);
        frame.nested.extend(alt);
        let call = arguments_to_call(&arguments);
        let mut text = format!(
            "    options = {{'{main_key}': {}}}\n    options['helpers'] = helpers\n    options['partials'] = partials\n    options['root'] = root\n",
            wrap_nested(&name)
        );
        // Writing to a String cannot fail.
        let _ = match alt_name {
            Some(alt_name) => writeln!(
                text,
                "    options['{alt_key}'] = {}",
                wrap_nested(&alt_name)
            ),
            None => writeln!(text, "    options['{alt_key}'] = lambda this: None"),
        };
        let symbol = &block.symbol;
        let _ = write!(
            text,
            "    value = helper = helpers.get(u'{symbol}')\n    if value is None:\n        value = resolve(context, u'{symbol}')\n    if helper and hasattr(helper, '__call__'):\n        value = helper(context, options{call}\n    else:\n        value = helpers['blockHelperMissing'](context, options, value)\n    result.grow(value or '')\n"
        );
        self.grow(&text);
        Ok(())
    }

    /// `add_rawblock`.
    fn raw_block(&mut self, symbol: &str, arguments: &[Arg], raw: &str) {
        let arguments: Vec<String> = arguments.iter().map(arg_code).collect();
        let call = arguments_to_call(&arguments);
        let raw = repr_str(raw, self.chars);
        let _ = write!(
            self.top().lines,
            "    options = {{'fn': lambda this: {raw}}}\n    options['helpers'] = helpers\n    options['partials'] = partials\n    options['root'] = root\n    options['inverse'] = lambda this: None\n    helper = helpers.get(u'{symbol}')\n    if helper and hasattr(helper, '__call__'):\n        value = helper(context, options{call}\n    else:\n        value = {raw}\n    result.grow(value or '')\n"
        );
    }

    /// `add_partial`.
    fn partial(&mut self, name: &Arg, arguments: &[Arg]) -> Result<(), ExtraPositionalArgument> {
        let symbol = complex_arg(name);
        let arguments: Vec<String> = arguments.iter().map(arg_code).collect();
        let mut positional: Option<&str> = None;
        let mut overrides: Vec<(&str, &str)> = Vec::new();
        for argument in &arguments {
            match keyword_match(argument, self.chars) {
                Some((key, value)) => match overrides.iter_mut().find(|(k, _)| *k == key) {
                    Some(entry) => entry.1 = value,
                    None => overrides.push((key, value)),
                },
                None if positional.is_some() => return Err(ExtraPositionalArgument),
                None => positional = Some(argument),
            }
        }
        let overrides_literal = if overrides.is_empty() {
            "None".to_owned()
        } else {
            let mut literal = String::from("{");
            for (key, value) in &overrides {
                let _ = write!(literal, "\"{key}\": {value}, ");
            }
            literal.push('}');
            literal
        };
        let arg = match positional {
            Some(arg) if !arg.is_empty() => arg,
            _ => "context",
        };
        self.grow(&format!(
            "    overrides = {overrides_literal}\n    partialName = {symbol}\n    if partialName not in partials:\n        raise PybarsError('The partial %s could not be found' % partialName)\n    inner = partials[partialName]\n    scope = Scope({arg}, context, root, overrides=overrides)\n    result.grow(inner(scope, helpers=helpers, partials=partials, root=root))\n"
        ));
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keyword_matching_follows_python_re() {
        let chars = Chars::new(crate::UnicodeVersion::LATEST);
        let keyword = |argument| keyword_match(argument, chars);
        assert_eq!(keyword("ab=1"), Some(("ab", "1")));
        assert_eq!(keyword("ab=x\n"), Some(("ab", "x")));
        assert_eq!(keyword("ab=x\ny"), None);
        assert_eq!(keyword("ab="), None);
        assert_eq!(keyword("resolve(context, u'a=b')"), None);
        assert_eq!(keyword("é_1=v"), Some(("é_1", "v")));
    }

    #[test]
    fn calls_list_arguments() {
        assert_eq!(arguments_to_call(&[]), ")");
        assert_eq!(
            arguments_to_call(&["a".into(), String::new()]),
            ", a, context)"
        );
    }
}
