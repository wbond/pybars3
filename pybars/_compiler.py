#
# Copyright (c) 2012, Canonical Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, version 3 only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# GNU Lesser General Public License version 3 (see the file LICENSE).

"""The compiler for pybars."""


__all__ = [
    'Compiler',
    'strlist',
    ]

__metaclass__ = type

from functools import partial
import re

import pybars
from pymeta.grammar import OMeta
from pybars.frompymeta import moduleFromSource

# preserve reference to the builtin compile.
_compile = compile

# Note that unless we presume handlebars is only generating valid html, we have
# to accept anything - so a broken template won't be all that visible - it will
# just render literally (because the anything rule matches it).

# this grammar generates a tokenised tree
handlebars_grammar = r"""

template ::= (<text> | <templatecommand>)*:body => ['template'] + body
text ::= (~(<start>) <anything>)+:text => ('literal', u''.join(text))
other ::= <anything>:char => ('literal', char)
templatecommand ::= <blockrule>
    | <comment>
    | <escapedexpression>
    | <expression>
    | <partial>
start ::= '{' '{'
finish ::= '}' '}'
comment ::= <start> '!' (~(<finish>) <anything>)* <finish> => ('comment', )
space ::= ' '|'\t'|'\r'|'\n'
arguments ::= (<space>+ (<kwliteral>|<literal>|<path>))*:arguments => arguments
expression_inner ::= <spaces> <path>:p <arguments>:arguments <spaces> <finish> => (p, arguments)
expression ::= <start> '{' <expression_inner>:e '}' => ('expand', ) + e
    | <start> '&' <expression_inner>:e => ('expand', ) + e
escapedexpression ::= <start> <expression_inner>:e => ('escapedexpand', ) + e
block_inner ::= <spaces> <symbol>:s <arguments>:args <spaces> <finish>
    => (u''.join(s), args)
partial ::= <start> '>' <block_inner>:i => ('partial',) + i
path ::= ~('/') <pathseg>+:segments => ('path', segments)
kwliteral ::= <symbol>:s '=' (<literal>|<path>):v => ('kwparam', s, v)
literal ::= (<string>|<integer>|<boolean>):thing => ('literalparam', thing)
string ::= '"' <notquote>*:ls '"' => u'"' + u''.join(ls) + u'"'
integer ::= <digit>+:ds => int(''.join(ds))
boolean ::= <false>|<true>
false ::= 'f' 'a' 'l' 's' 'e' => False
true ::= 't' 'r' 'u' 'e' => True
notquote ::= <escapedquote> | (~('"') <anything>)
escapedquote ::= '\\' '"' => '\\"'
symbol ::= '['? (<letterOrDigit>|'-'|'@')+:symbol ']'? => u''.join(symbol)
pathseg ::= <symbol>
    | '/' => u''
    | ('.' '.' '/') => u'__parent'
    | '.' => u''
pathfinish :expected ::= <start> '/' <path>:found ?(found == expected) <finish>
symbolfinish :expected ::= <start> '/' <symbol>:found ?(found == expected) <finish>
blockrule ::= <start> '#' <block_inner>:i
      <template>:t <alttemplate>:alt_t <symbolfinish i[0]> => ('block',) + i + (t, alt_t)
    | <start> '^' <block_inner>:i
      <template>:t <symbolfinish i[0]> => ('invertedblock',) + i + (t,)
alttemplate ::= (<start>'^'<finish> <template>)?:alt_t => alt_t or []
"""

# this grammar compiles the template to python
compile_grammar = """
compile ::= <prolog> <rule>* => builder.finish()
prolog ::= "template" => builder.start()
rule ::= <literal>
    | <expand>
    | <escapedexpand>
    | <comment>
    | <block>
    | <invertedblock>
    | <partial>
block ::= [ "block" <anything>:symbol [<arg>*:arguments] [<compile>:t] [<compile>?:alt_t] ] => builder.add_block(symbol, arguments, t, alt_t)
comment ::= [ "comment" ]
literal ::= [ "literal" :value ] => builder.add_literal(value)
expand ::= [ "expand" <path>:value [<arg>*:arguments]] => builder.add_expand(value, arguments)
escapedexpand ::= [ "escapedexpand" <path>:value [<arg>*:arguments]] => builder.add_escaped_expand(value, arguments)
invertedblock ::= [ "invertedblock" <anything>:symbol [<arg>*:arguments] [<compile>:t] ] => builder.add_invertedblock(symbol, arguments, t)
partial ::= ["partial" <anything>:symbol [<arg>*:arguments]] => builder.add_partial(symbol, arguments)
path ::= [ "path" [<pathseg>:segment]] => ("simple", segment)
 | [ "path" [<pathseg>+:segments] ] => ("complex", u'resolve(context, "'  + u'","'.join(segments) + u'")' )
simplearg ::= [ "path" [<pathseg>+:segments] ] => u'resolve(context, "'  + u'","'.join(segments) + u'")'
    | [ "literalparam" <anything>:value ] => unicode(value)
arg ::= [ "kwparam" <anything>:symbol <simplearg>:a ] => unicode(symbol) + '=' + a
    | <simplearg>
pathseg ::= "/" => ''
    | "." => ''
    | "" => ''
    | "this" => ''
pathseg ::= <anything>:symbol => u''.join(symbol)
"""


class strlist(list):
    """A quasi-list to let the template code avoid special casing."""

    def __unicode__(self):
        return u''.join(self)

    def grow(self, thing):
        """Make the list longer, appending for unicode, extending otherwise."""
        if type(thing) == unicode:
            self.append(thing)
        elif type(thing) == str:
            # Ugh. Kill this in 3.
            self.append(unicode(thing))
        else: 
            # Recursively expand to a flat list; may deserve a C accelerator at
            # some point.
            for element in thing:
                self.grow(element)


_map = {
    '&':'&amp;',
    '"':'&quot;',
    '\'':'&#x27;',
    '`':'&#x60;',
    '<':'&lt;',
    '>':'&gt;',
    }
def substitute(match, _map=_map):
    return _map[match.group(0)]


_escape_re = re.compile(r"&|\"|'|`|<|>")
def escape(something, _escape_re=_escape_re, substitute=substitute):
    return _escape_re.sub(substitute, something)


sentinel = object()

class Scope:

    def __init__(self, context, parent):
        self.context = context
        self.parent = parent

    def get(self, name, default=None):
        if name == '__parent':
            return self.parent
        if name == 'this':
            return self.context
        result = self.context.get(name, self)
        if result is not self:
            return result
        return default
    __getitem__ = get

    def __unicode__(self):
        return unicode(self.context)


def resolve(context, *segments):
    for segment in segments:
        if context is None:
            return None
        if segment in (None, ""):
            continue
        if type(context) in (list, tuple):
            offset = int(segment)
            context = context[offset]
        else:
            context = context.get(segment)
    return context


def _each(this, options, context):
    result = strlist()
    for local_context in context:
        scope = Scope(local_context, this)
        result.grow(options['fn'](scope))
    return result


def _if(this, options, context):
    if callable(context):
        context = context(this)
    if context:
        return options['fn'](this)


def _log(this, context):
    pybars.log(context)


def _unless(this, options, context):
    if not context:
        return options['fn'](this)


def _blockHelperMissing(this, options, context):
    # print this, context
    if callable(context):
        context = context(this)
    if context != u"" and not context:
        return options['inverse'](this)
    if type(context) in (list, strlist, tuple):
        return _each(this, options, context)
    if context is True:
        callwith = this
    else:
        callwith = context
    return options['fn'](callwith)


def _with(this, options, context):
    return options['fn'](context)

# scope for the compiled code to reuse globals
_pybars_ = {
    'helpers': {
        'blockHelperMissing': _blockHelperMissing,
        'each': _each,
        'if': _if,
        'log': _log,
        'unless': _unless,
        'with': _with,
    }
}

class CodeBuilder:
    """Builds code for a template."""

    def __init__(self):
        self.stack = []

    def start(self):
        self.stack.append((strlist(), {}))
        self._result, self._locals = self.stack[-1]
        # Context may be a user hash or a Scope (which injects '__parent' to
        # implement .. lookups). The JS implementation uses a vector of scopes
        # and then interprets a linear walk-up, which is why there is a
        # disabled test showing arbitrary complex path manipulation: the scope
        # approach used here will probably DTRT but may be slower: reevaluate
        # when profiling.
        self._result.grow(u"def render(context, helpers=None, partials=None):\n")
        self._result.grow(u"    result = strlist()\n")
        self._result.grow(u"    if helpers is None: helpers = {}\n")
        self._result.grow(u"    helpers.update(pybars['helpers'])\n")
        self._result.grow(u"    if partials is None: partials = {}\n")
        # Expose used functions and helpers to the template.
        self._locals['strlist'] = strlist
        self._locals['escape'] = escape
        self._locals['Scope'] = Scope
        self._locals['partial'] = partial
        self._locals['pybars'] = _pybars_
        self._locals['resolve'] = resolve

    def finish(self):
        self._result.grow(u"    return result\n")
        lines, ns = self.stack.pop(-1)
        source = unicode(lines)
        self._result = self.stack and self.stack[-1][0]
        self._locals = self.stack and self.stack[-1][1]
        fn = moduleFromSource(source, 'render', globalsDict=ns, registerModule=True)
        # print source
        return fn

    def allocate_value(self, value):
        name = 'constant_%d' % len(self._locals)
        self._locals[name] = value
        return name

    def _wrap_nested(self, name):
        return u"partial(%s, helpers=helpers, partials=partials)" % name

    def add_block(self, symbol, arguments, nested, alt_nested):
        name = self.allocate_value(nested)
        if alt_nested:
            alt_name = self.allocate_value(alt_nested)
        call = self.arguments_to_call(arguments)
        self._result.grow([
            u"    options = {'fn': %s}\n" % self._wrap_nested(name),
            u"    options['helpers'] = helpers\n"
            u"    options['partials'] = partials\n"
            ])
        if alt_nested:
            self._result.grow([
                u"    options['inverse'] = ",
                self._wrap_nested(alt_name),
                u"\n"
                ])
        else:
            self._result.grow([
                u"    options['inverse'] = lambda this: None\n"
                ])
        self._result.grow([
            u"    value = helper = helpers.get('%s')\n" % symbol,
            u"    if value is None:\n"
            u"        value = context.get('%s')\n" % symbol,
            u"    if helper and callable(helper):\n"
            u"        this = Scope(context, context)\n"
            u"        value = value(this, options, %s\n" % call,
            u"    else:\n"
            u"        helper = helpers['blockHelperMissing']\n"
            u"        value = helper(context, options, value)\n"
            u"    if value is None: value = ''\n"
            u"    result.grow(value)\n"
            ])

    def add_literal(self, value):
        name = self.allocate_value(value)
        self._result.grow(u"    result.append(%s)\n" % name)

    def _lookup_arg(self, arg):
        if not arg:
            return u"context"
        return arg

    def arguments_to_call(self, arguments):
        params = map(self._lookup_arg, arguments)
        return u", ".join(params) + ")"

    def find_lookup(self, path, path_type, call):
        if path and path_type == "simple": # simple names can reference helpers.
            # TODO: compile this whole expression in the grammar; for now,
            # fugly but only a compile time overhead.
            # XXX: just rm.
            realname = path.replace('.get("', '').replace('")', '')
            self._result.grow([
                u"    value = helpers.get('%s')\n" % realname,
                u"    if value is None:\n"
                u"        value = resolve(context, '%s')\n" % path,
                ])
        elif path_type == "simple":
            realname = None
            self._result.grow([
                u"    value = resolve(context, '%s')\n" % path,
                ])
        else:
            realname = None
            self._result.grow(u"    value = %s\n" % path)
        self._result.grow([
            u"    if callable(value):\n"
            u"        this = Scope(context, context)\n"
            u"        value = value(this, %s\n" % call,
            ])
        if realname:
            self._result.grow(
                u"    elif value is None:\n"
                u"        this = Scope(context, context)\n"
                u"        value = helpers.get('helperMissing')(this, '%s', %s\n"
                    % (realname, call)
                )
        self._result.grow(u"    if value is None: value = ''\n")

    def add_escaped_expand(self, (path_type, path), arguments):
        call = self.arguments_to_call(arguments)
        self.find_lookup(path, path_type, call)
        self._result.grow([
            u"    if type(value) is not strlist:\n"
            u"        value = escape(unicode(value))\n"
            u"    result.grow(value)\n"
            ])

    def add_expand(self, (path_type, path), arguments):
        call = self.arguments_to_call(arguments)
        self.find_lookup(path, path_type, call)
        self._result.grow([
            u"    if type(value) is not strlist:\n"
            u"        value = unicode(value)\n"
            u"    result.grow(value)\n"
            ])

    def _debug(self):
        self._result.grow(u"    import pdb;pdb.set_trace()\n")

    def add_invertedblock(self, symbol, arguments, nested):
        # This may need to be a blockHelperMissing clal as well.
        name = self.allocate_value(nested)
        self._result.grow([
            u"    value = context.get('%s')\n" % symbol,
            u"    if not value:\n"
            u"    "])
        self._invoke_template(name, "context")

    def _invoke_template(self, fn_name, this_name):
        self._result.grow([
            u"    result.grow(",
            fn_name,
            u"(",
            this_name,
            u", helpers=helpers, partials=partials))\n"
            ])

    def add_partial(self, symbol, arguments):
        if arguments:
            assert len(arguments) == 1, arguments
            arg = arguments[0]
        else:
            arg = ""
        self._result.grow([
            u"    inner = partials['%s']\n" % symbol,
            u"    scope = Scope(%s, context)\n" % self._lookup_arg(arg)])
        self._invoke_template("inner", "scope")


# TODO: move to a better home
global_helpers = {}

class Compiler:
    """A handlebars template compiler.
    
    The compiler is not threadsafe: you need one per thread because of the
    state in CodeBuilder.
    """

    _handlebars = OMeta.makeGrammar(handlebars_grammar, {}, 'handlebars')
    _builder = CodeBuilder()
    _compiler = OMeta.makeGrammar(compile_grammar, {'builder':_builder})

    def __init__(self):
        self._helpers = {}

    def compile(self, source):
        """Compile source to a ready to run template.
        
        :param source: The template to compile - should be a unicode string.
        :return: A template ready to run.
        """
        assert isinstance(source, unicode)
        tree = self._handlebars(source).apply('template')[0]
        # print source
        # print '-->'
        # print "T", tree
        code = self._compiler(tree).apply('compile')[0]
        # print code
        return code

    def register_helper(self, helper_name, helper_callback):
        """Register a block helper.

        :param helper_name: The name of the helper.
        :param helper_callback: A callback to call when the helper is used.
            This should accept two parameters - items (the context sub-value
            specified by the block rule in the template) and options (which has
            template logic in it such as the render callback to render the
            block content for a single item).
        :return: None
        """
        global_helpers[helper_name] = helper_callback

#orig = Compiler._handlebars.rule_blockrule
#def thunk(*args, **kwargs):
#    import pdb;pdb.set_trace()
#    return orig(*args, **kwargs)
#Compiler._handlebars.rule_blockrule = thunk
