#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2015 Will Bond, Mjumbe Wawatu Ukweli, 2011 by Yehuda Katz
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""A port of the acceptance test for handlebars.js."""

from unittest import TestCase

try:
    str_class = unicode
except NameError:
    # Python 3 support
    str_class = str

import sys
import os

import pybars
from pybars import (
    strlist,
    Scope,
    PybarsError,
    Compiler
    )
from .test__compiler import render


class TestAcceptance(TestCase):

    def assertRender(self, template, context, result, helpers=None, partials=None, error=None, **kwargs):
        try:
            self.assertEqual(result, render(template, context, helpers=helpers, partials=partials, **kwargs))
        except PybarsError as e:
            self.assertEqual(str(e), error)
        else:
            if error:
                self.assertTrue(False, "Was expecting an error: {}".format(error))

    def test_basic_context(self):
        template = u"Goodbye\n{{cruel}}\n{{world}}!"
        context = {
            'cruel': "cruel",
            'world': "world"
        }
        result = u"Goodbye\ncruel\nworld!"

        self.assertRender(template, context, result)

    def test_basic_unicode_context(self):
        template = u"وداعا أيها {{العالم}} {{القاسي}}!"
        context = {
            u"القاسي": u"القاسي",
            u"العالم": u"العالم"
        }
        result = u"وداعا أيها العالم القاسي!"
        self.assertRender(template, context, result)

    def test_comments_ignored(self):
        template = u"{{! Goodbye}}Goodbye\n{{cruel}}\n{{world}}!"
        context = {
            'cruel': "cruel",
            'world': "world"
        }
        result = u"Goodbye\ncruel\nworld!"

        self.assertRender(template, context, result)

    def test_unicode_comments_ignored(self):
        template = u"{{! مع السلامه}}Goodbye\n{{cruel}}\n{{world}}!"
        context = {
            'cruel': "cruel",
            'world': "world"
        }
        result = u"Goodbye\ncruel\nworld!"

        self.assertRender(template, context, result)

    def test_booleans(self):
        template = u"{{#goodbye}}GOODBYE {{/goodbye}}cruel {{world}}!"

        context = {
            'goodbye': True,
            'world': 'world'
        }
        result = u"GOODBYE cruel world!"
        self.assertRender(template, context, result)

        context = {
            'goodbye': False,
            'world': 'world'
        }
        result = u"cruel world!"
        self.assertRender(template, context, result)

    def test_unicode_boolean_block(self):
        template = u"{{#وداعا}}GOODBYE {{/وداعا}}cruel {{world}}!"

        context = {
            u'وداعا': True,
            'world': 'world'
        }
        result = u"GOODBYE cruel world!"
        self.assertRender(template, context, result)

        context = {
            u'وداعا': False,
            'world': 'world'
        }
        result = u"cruel world!"
        self.assertRender(template, context, result)

    def test_zeros(self):
        template = u"num1: {{num1}}, num2: {{num2}}"
        context = {
            'num1': 42,
            'num2': 0
        }
        result = u"num1: 42, num2: 0"

        self.assertRender(template, context, result)

        template = u"num: {{.}}"
        context = 0
        result = u"num: 0"
        self.assertRender(template, context, result)

        template = u"num: {{num1/num2}}"
        context = {
            'num1': {
                'num2': 0
            }
        }
        result = u"num: 0"
        self.assertRender(template, context, result)

    def test_negative_int_literal(self):
        helpers = {
            'type': lambda s, v: type(v).__name__
        }

        template = u"{{type \"string\"}} {{type 1}} {{type -1}}"
        result = u"str int int"

        self.assertRender(template, None, result, helpers)

        helpers = {
            'echo': lambda s, v: str(v)
        }

        template = u"{{echo \"string\"}} {{echo 1}} {{echo -1}}"
        result = u"string 1 -1"

        self.assertRender(template, None, result, helpers)

    def test_newlines(self):
        template = u"Alan's\nTest"
        result = u"Alan's\nTest"

        self.assertRender(template, None, result)

        template = u"Alan's\rTest"
        result = u"Alan's\rTest"

        self.assertRender(template, None, result)

    def test_escaping_text(self):
        template = u"Awesome's"
        result = u"Awesome's"

        self.assertRender(template, None, result)

        template = u"Awesome\\"
        result = u"Awesome\\"

        self.assertRender(template, None, result)

        template = u"Awesome\\\\ foo"
        result = u"Awesome\\\\ foo"

        self.assertRender(template, None, result)

        template = u"Awesome {{foo}}"
        context = {
            'foo': '\\'
        }
        result = u"Awesome \\"

        self.assertRender(template, context, result)

        template = u' " " '
        result = u' " " '

        self.assertRender(template, None, result)

    def test_escaping_expressions(self):
        template = u"{{{awesome}}}"
        context = {
            'awesome': "&\"\\<>"
        }
        result = '&\"\\<>'

        self.assertRender(template, context, result)

        template = u"{{&awesome}}"
        context = {
            'awesome': "&\"\\<>"
        }
        result = '&\"\\<>'

        self.assertRender(template, context, result)

        template = u"{{awesome}}"
        context = {
            'awesome': "&\"'`\\<>"
        }
        result = u'&amp;&quot;&#x27;&#x60;\\&lt;&gt;'

        self.assertRender(template, context, result)

    def test_functions_returning_safestrings(self):
        template = u'{{awesome}}'
        result = '&\"\\<>'
        # Note that we use strlist for our safestring implementation.
        context = {
            'awesome': lambda this: strlist([result])
        }

        self.assertRender(template, context, result)

    def test_functions_called(self):
        result = 'Awesome'

        template = u'{{awesome}}'
        context = {
            'awesome': lambda this: result
        }

        self.assertRender(template, context, result)

        template = u'{{{awesome}}}'
        context = {
            'awesome': lambda this: result
        }

        self.assertRender(template, context, result)

    def test_functions_can_take_context_arguments(self):

        def awesome(this, context):
            return context

        template = u"{{awesome frank}}"
        context = {
            'awesome': awesome,
            'frank': 'Frank'
        }
        result = u"Frank"

        self.assertRender(template, context, result)

        template = u"{{{awesome frank}}}"
        context = {
            'awesome': awesome,
            'frank': 'Frank'
        }
        result = u"Frank"

        self.assertRender(template, context, result)

    def test_pathed_functions_with_context_arguments(self):
        def awesome(this, context):
            return context

        template = u"{{bar.awesome frank}}"
        context = {
            'bar': {
                'awesome': awesome,
            },
            'frank': 'Frank'
        }
        result = u"Frank"

        self.assertRender(template, context, result)

    def test_unicode_pathed_functions_with_context_arguments(self):
        def awesome(this, context):
            return context

        template = u"{{بار.رائع frank}}"
        context = {
            u'بار': {
                u'رائع': awesome,
            },
            'frank': 'Frank'
        }
        result = u"Frank"

        self.assertRender(template, context, result)

    def test_block_functions_without_context_arguments(self):
        def awesome(this):
            return this

        template = u"{{#awesome}}inner{{/awesome}}"
        context = {
            'awesome': awesome
        }
        result = u"inner"

        self.assertRender(template, context, result)

    def test_paths_can_contain_hyphens(self):
        template = u"{{foo-bar}}"
        context = {
            "foo-bar": "baz"
        }
        result = u"baz"

        self.assertRender(template, context, result)

        template = u"{{foo.foo-bar}}"
        context = {
            'foo': {
                'foo-bar': 'baz'
            }
        }
        result = u"baz"

        self.assertRender(template, context, result)

        template = u"{{foo/foo-bar}}"
        context = {
            'foo': {
                'foo-bar': 'baz'
            }
        }
        result = u"baz"

        self.assertRender(template, context, result)

    def test_unicode_paths_can_contain_hyphens(self):
        template = u"{{فوو-بار}}"
        context = {
            u"فوو-بار": "baz"
        }
        result = u"baz"

        self.assertRender(template, context, result)

        template = u"{{فوو.فوو-بار}}"
        context = {
            u"فوو": {
                u"فوو-بار": u"باز"
            }
        }
        result = u"باز"

        self.assertRender(template, context, result)

        template = u"{{فوو/فوو-بار}}"
        context = {
            u"فوو": {
                u"فوو-بار": u"باز"
            }
        }
        result = u"باز"

        self.assertRender(template, context, result)

    def test_nested_paths_access_nested_objects(self):
        template = u"Goodbye {{alan/expression}} world!"
        context = {
            'alan': {
                'expression': 'beautiful'
            }
        }
        result = u"Goodbye beautiful world!"

        self.assertRender(template, context, result)

    def test_nested_paths_to_empty_string_renders(self):
        template = u"Goodbye {{alan/expression}} world!"
        context = {
            'alan': {
                'expression': ''
            }
        }
        result = u"Goodbye  world!"

        self.assertRender(template, context, result)

    def test_literal_paths_can_be_used(self):
        template = u"Goodbye {{[@alan]/expression}} world!"
        context = {
            '@alan': {
                'expression': 'beautiful'
            }
        }
        result = u"Goodbye beautiful world!"

        self.assertRender(template, context, result)

        template = u"Goodbye {{[foo bar]/expression}} world!"
        context = {
            'foo bar': {
                'expression': 'beautiful'
            }
        }
        result = u"Goodbye beautiful world!"
        self.assertRender(template, context, result)

    def test_unicode_literal_paths_can_be_used(self):
        template = u"Goodbye {{[@اسحق]/expression}} world!"
        context = {
            u"@اسحق": {
                'expression': 'beautiful'
            }
        }
        result = u"Goodbye beautiful world!"

        self.assertRender(template, context, result)

        template = u"Goodbye {{[فوو بار]/expression}} world!"
        context = {
            u"فوو بار": {
                'expression': 'beautiful'
            }
        }
        result = u"Goodbye beautiful world!"
        self.assertRender(template, context, result)

    def test_nested_paths(self):
        template = u"{{#goodbyes}}{{.././world}} {{/goodbyes}}"
        context = {
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ],
            'world': "world"
        }
        result = u"world world world "

        self.assertRender(template, context, result)

    def test_current_context_does_not_invoke_helpers(self):
        helpers = {'helper': "notcallable"}

        template = u"test: {{.}}"
        result = u"test: "

        self.assertRender(template, None, result, helpers)

    def test_complex_but_empty_paths(self):
        template = u"{{person/name}}"
        context = {
            'person': {
                'name': None
            }
        }
        result = u""

        self.assertRender(template, context, result)

        template = u"{{person/name}}"
        context = {
            'person': {}
        }
        result = u""

        self.assertRender(template, context, result)

    def test_this_keyword_in_paths_simple(self):
        template = u"{{#goodbyes}}{{this}}{{/goodbyes}}"
        context = {
            'goodbyes': [
                "goodbye",
                "Goodbye",
                "GOODBYE"
            ]
        }
        result = u"goodbyeGoodbyeGOODBYE"

        self.assertRender(template, context, result)

    def test_this_keyword_in_paths_complex(self):
        template = u"{{#hellos}}{{this/text}}{{/hellos}}"
        context = {
            'hellos': [
                {'text': 'hello'},
                {'text': 'Hello'},
                {'text': "HELLO"}
            ]
        }
        result = u"helloHelloHELLO"

        self.assertRender(template, context, result)

    def test_this_keyword_in_helpers(self):
        def helper(this, value):
            return 'bar ' + value
        helpers = {
            'foo': helper
        }
        template = u"{{#goodbyes}}{{foo this}}{{/goodbyes}}"
        context = {
            'goodbyes': ['goodbye', 'Goodbye', 'GOODBYE']
        }
        result = u"bar goodbyebar Goodbyebar GOODBYE"

        self.assertRender(template, context, result, helpers=helpers)

        template = u"{{#hellos}}{{foo this/text}}{{/hellos}}"
        context = {
            'hellos': [{'text': 'hello'}, {'text': 'Hello'}, {'text': 'HELLO'}]
        }
        result = u"bar hellobar Hellobar HELLO"

        self.assertRender(template, context, result, helpers=helpers)

    def test_pass_number_literal(self):
        self.assertRender(u"{{12}}", {}, u"")
        self.assertRender(u"{{12}}", {'12': 'bar'}, u"bar")
        self.assertRender(u"{{12.34}}", {}, u"")
        # FIXME the two cases below currently fail, it is also the case for non-numeric variables
        # self.assertRender(u"{{12.34}}", {'12.34': 'bar'}, u"bar")
        # def func(this, arg):
        #     return 'bar' + str(arg)
        # self.assertRender(u"{{12.34 1}}", {'12.34': func}, u"bar1")

    def test_pass_boolean_literal(self):
        self.assertRender(u"{{true}}", {}, u"")
        self.assertRender(u"{{true}}", {'': 'foo'}, u"")
        self.assertRender(u"{{false}}", {'false': 'foo'}, u"foo")

    def test_inverted_sections(self):
        # We use this form to not introduce extra whitespace
        template = (
            u"{{#goodbyes}}{{this}}{{/goodbyes}}"
            u"{{^goodbyes}}Right On!{{/goodbyes}}"
        )
        result = u"Right On!"

        context = {}

        self.assertRender(template, context, result)

        context = {'goodbyes': False}

        self.assertRender(template, context, result)

        context = {'goodbyes': []}

        self.assertRender(template, context, result)

    def test_unicode_inverted_sections(self):
        # We use this form to not introduce extra whitespace
        template = (
            u"{{#سلامات}}{{this}}{{/سلامات}}"
            u"{{^سلامات}}Right On!{{/سلامات}}"
        )
        result = u"Right On!"

        context = {}

        self.assertRender(template, context, result)

        context = {u'سلامات': False}

        self.assertRender(template, context, result)

        context = {u'سلامات': []}

        self.assertRender(template, context, result)

    def test_inverted_alternate_sections(self):
        # We use this form to not introduce extra whitespace
        template = (
            u"{{#goodbyes}}{{this}}{{else}}Right On!{{/goodbyes}}\n"
            u"{{^goodbyes}}Right On!{{else}}{{this}}{{/goodbyes}}"
        )
        result = "Right On!\nRight On!"

        self.assertRender(template, {}, result)
        self.assertRender(template, {'goodbyes': False}, result)
        self.assertRender(template, {'goodbyes': []}, result)

        self.assertRender(template, {'goodbyes': ['Hello', 'world!']}, u"Helloworld!\nHelloworld!")

    def test_unicode_inverted_alternate_sections(self):
        # We use this form to not introduce extra whitespace
        template = (
            u"{{#سلامات}}{{this}}{{else}}Right On!{{/سلامات}}\n"
            u"{{^سلامات}}Right On!{{else}}{{this}}{{/سلامات}}"
        )
        result = "Right On!\nRight On!"

        self.assertRender(template, {}, result)
        self.assertRender(template, {u'سلامات': False}, result)
        self.assertRender(template, {u'سلامات': []}, result)

        self.assertRender(template, {u'سلامات': ['Hello', 'world!']}, u"Helloworld!\nHelloworld!")

    def test_array_iteration(self):
        template = u"{{#goodbyes}}{{text}}! {{/goodbyes}}cruel {{world}}!"

        context = {
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ],
            'world': "world"
        }
        result = u"goodbye! Goodbye! GOODBYE! cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbyes': [],
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

    def test_unicode_array_iteration(self):
        template = u"{{#سلامات}}{{النص}}! {{/سلامات}}cruel {{world}}!"

        context = {
            u'سلامات': [
                {u'النص': "goodbye"},
                {u'النص': "Goodbye"},
                {u'النص': "GOODBYE"}
            ],
            'world': "world"
        }
        result = u"goodbye! Goodbye! GOODBYE! cruel world!"

        self.assertRender(template, context, result)

        context = {
            'سلامات': [],
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

    def test_empty_block(self):
        template = u"{{#goodbyes}}{{/goodbyes}}cruel {{world}}!"

        context = {
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ],
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbyes': [],
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

    def test_nested_iteration(self):
        # Empty upstream
        pass

    def test_block_with_complex_lookup(self):
        template = u"{{#goodbyes}}{{text}} cruel {{../name}}! {{/goodbyes}}"
        context = {
            'name': "Alan",
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ]
        }
        result = u"goodbye cruel Alan! Goodbye cruel Alan! GOODBYE cruel Alan! "

        self.assertRender(template, context, result)

    def test_parent_lookup(self):
        template = u"{{#goodbyes}}{{text}} cruel {{@_parent.name}}! {{/goodbyes}}"
        context = {
            'name': "Alan",
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ]
        }
        result = u"goodbye cruel Alan! Goodbye cruel Alan! GOODBYE cruel Alan! "

        self.assertRender(template, context, result)

    def test_helper_with_complex_lookup(self):

        def link(this, prefix):
            return (u"<a href='" + prefix + u"/"
                + this.get('url') + u"'>"
                + this.get('text') + u"</a>")

        helpers = {'link': link}

        template = u"{{#goodbyes}}{{{link ../prefix}}}{{/goodbyes}}"
        context = {
            'prefix': "/root",
            'goodbyes': [
                {
                    'text': "Goodbye",
                    'url': "goodbye"
                }
            ]
        }
        result = u"<a href='/root/goodbye'>Goodbye</a>"

        self.assertRender(template, context, result, helpers)

    def test_helper_block_with_complex_lookup(self):
        def goodbyes(this, options):
            result = strlist()
            for bye in ["Goodbye", "goodbye", "GOODBYE"]:
                result.grow(bye)
                result.grow(' ')
                result.grow(options['fn'](this))
                result.grow("! ")
            return result

        helpers = {'goodbyes': goodbyes}

        template = u"{{#goodbyes}}{{../name}}{{/goodbyes}}"
        context = {
            'name': "Alan"
        }
        result = u"Goodbye Alan! goodbye Alan! GOODBYE Alan! "

        self.assertRender(template, context, result, helpers)

    def test_helper_with_complex_lookup_and_nested_template(self):

        def link(this, options, prefix):
            return u"<a href='" + str_class(prefix) + u"/" + this['url'] + u"'>" + str_class(options['fn'](this)) + u"</a>"

        helpers = {'link': link}

        template = u"{{#goodbyes}}{{#link ../prefix}}{{text}}{{/link}}{{/goodbyes}}"
        context = {
            'prefix': '/root',
            'goodbyes': [
                {
                    'text': "Goodbye",
                    'url': "goodbye"
                }
            ]
        }
        result = u"<a href='/root/goodbye'>Goodbye</a>"

        self.assertRender(template, context, result, helpers)

    def test_block_helper_with_deep_nested_lookup(self):

        def para(this, options, value):
            param = Scope(value, this, options['root'])
            if value:
                return strlist(['<p>']) + options['fn'](param) + strlist(['</p>'])

        helpers = {'para': para}

        template = (
            u"{{#para nested}}Goodbye "
            u"{{#if ../world}}cruel {{../world}}{{/if}}{{/para}}"
        )
        context = {
            'world': "world!",
            'nested': True
        }
        result = u"<p>Goodbye cruel world!</p>"

        self.assertRender(template, context, result, helpers)

    def test_block_with_deep_nested_complex_lookup(self):
        template = (
            u"{{#outer}}Goodbye "
            u"{{#inner}}cruel {{../../omg}}{{/inner}}{{/outer}}"
        )
        context = {
            'omg': "OMG!",
            'outer': [
                {
                    'inner': [
                        {'text': "goodbye"}
                    ]
                }
            ]
        }
        result = u"Goodbye cruel OMG!"

        self.assertRender(template, context, result)

    def test_root_lookup(self):
        template = (
            u"{{#outer}}Goodbye "
            u"{{#inner}}cruel {{@root.top}}{{/inner}}{{/outer}}"
        )
        context = {
            'top': "world",
            'outer': [
                {
                    'inner': [
                        {'text': "goodbye"}
                    ]
                }
            ]
        }
        result = u"Goodbye cruel world"

        self.assertRender(template, context, result)

    def test_block_helper(self):

        def goodbyes(this, options):
            return options['fn']({'text': "GOODBYE"})

        helpers = {'goodbyes': goodbyes}

        template = u"{{#goodbyes}}{{text}}! {{/goodbyes}}cruel {{world}}!"
        context = {
            'world': "world"
        }
        result = u"GOODBYE! cruel world!"

        self.assertRender(template, context, result, helpers)

    def test_block_helper_staying_in_the_same_context(self):

        def form(this, options):
            return strlist([u"<form>", options['fn'](this), u"</form>"])

        helpers = {'form': form}

        template = u"{{#form}}<p>{{name}}</p>{{/form}}"
        context = {
            'name': "Yehuda"
        }
        result = u"<form><p>Yehuda</p></form>"

        self.assertRender(template, context, result, helpers)

    def test_block_helper_should_have_context_in_this(self):

        def link(this, options):
            return strlist((
                '<a href="/people/', str_class(this['id']), '">',
                options['fn'](this),
                '</a>'
            ))

        helpers = {'link': link}

        template = u"<ul>{{#people}}<li>{{#link}}{{name}}{{/link}}</li>{{/people}}</ul>"
        context = {
            "people": [
                {
                    "name": "Alan",
                    "id": 1
                },
                {
                    "name": "Yehuda",
                    "id": 2
                }
            ]
        }
        result = (
            "<ul><li><a href=\"/people/1\">Alan</a></li>"
            "<li><a href=\"/people/2\">Yehuda</a></li></ul>"
        )

        self.assertRender(template, context, result, helpers)

    def test_block_helper_for_undefined_value(self):
        template = u"{{#empty}}shouldn't render{{/empty}}"
        context = {}
        result = ''

        self.assertRender(template, context, result)

    def test_invalid_closing_tags(self):
        template = u'{{#foo}}{{/#foo}}'
        context = {}
        result = None
        error = 'Error at character 11 of line 1 near {{/#foo}}'

        self.assertRender(template, context, result, error=error)

    def test_missing_bracket(self):
        template = u'{{foo}'
        context = {}
        result = None
        error = 'Error at character 5 of line 1 near {{foo}'

        self.assertRender(template, context, result, error=error)

    def test_block_helper_passing_a_new_context(self):

        def form(this, options, context):
            return "<form>" + str_class(options['fn'](context)) + '</form>'

        helpers = {'form': form}

        template = u"{{#form yehuda}}<p>{{name}}</p>{{/form}}"
        context = {
            'yehuda': {
                'name': "Yehuda"
            }
        }
        result = u"<form><p>Yehuda</p></form>"

        self.assertRender(template, context, result, helpers)

    def test_block_helper_passing_a_complex_path_context(self):
        def form(this, options, context):
            return u"<form>" + str_class(options['fn'](context)) + u"</form>"

        helpers = {'form': form}

        template = u"{{#form yehuda/cat}}<p>{{name}}</p>{{/form}}"
        context = {
            'yehuda': {
                'name': "Yehuda",
                'cat': {
                    'name': "Harold"
                }
            }
        }
        result = u"<form><p>Harold</p></form>"

        self.assertRender(template, context, result, helpers)

    def test_subexpression(self):

        def para(this, options, values_dict):
            return strlist(u'<p>') + options['fn'](values_dict) + strlist(u'</p>')

        def fold(this, key, val):
            return {key: val}

        helpers = {
            'para': para,
            'fold': fold
        }

        template = u"{{#para (fold 'foo' val)}}{{foo}}{{/para}}"
        context = {
            'val': 'bar'
        }
        result = u"<p>bar</p>"

        self.assertRender(template, context, result, helpers)

    def test_nested_subexpression(self):

        def para(this, options, values_dict):
            return strlist(u'<p>') + options['fn'](values_dict) + strlist(u'</p>')

        def fold(this, key, val):
            return {key: val}

        def add(this, num1, num2):
            return num1 + num2

        helpers = {
            'para': para,
            'fold': fold,
            'add': add
        }

        template = u"{{#para (fold 'foo' (add val 1))}}{{foo}}{{/para}}"
        context = {
            'val': 1
        }
        result = u"<p>2</p>"

        self.assertRender(template, context, result, helpers)

    def test_subexpression_containing_keyword(self):

        def para(this, options, values_dict):
            return strlist(u'<p>') + options['fn'](values_dict) + strlist(u'</p>')

        def fold2(this, key, value=None):
            return {key: value}

        helpers = {
            'para': para,
            'fold2': fold2
        }

        template = u"{{#para (fold2 'foo' value=val)}}{{foo}}{{/para}}"
        context = {
            'val': 'bar'
        }
        result = u"<p>bar</p>"

        self.assertRender(template, context, result, helpers)

    def test_subexpression_as_keyword(self):

        def para2(this, options, blah=None, values_dict=None):
            return strlist(u'<p>') + options['fn'](values_dict) + strlist(u'</p>')

        def fold2(this, key, value=None):
            return {key: value}

        helpers = {
            'para2': para2,
            'fold2': fold2
        }

        template = u"{{#para2 values_dict=(fold2 'foo' value=val)}}{{foo}}{{/para2}}"
        context = {
            'val': 'bar'
        }
        result = u"<p>bar</p>"

        self.assertRender(template, context, result, helpers)

    def test_nested_block_helpers(self):

        def link(this, options):
            return (
                "<a href='" + this['name'] + "'>"
                + str_class(options['fn'](this)) + "</a>")

        def form(this, options, context):
            return "<form>" + str_class(options['fn'](context)) + "</form>"

        helpers = {
            'link': link,
            'form': form
        }

        template = u"{{#form yehuda}}<p>{{name}}</p>{{#link}}Hello{{/link}}{{/form}}"
        context = {
            'yehuda': {
                'name': "Yehuda"
            }
        }
        result = u"<form><p>Yehuda</p><a href='Yehuda'>Hello</a></form>"

        self.assertRender(template, context, result, helpers)

    def test_block_inverted_sections(self):
        template = u"{{#people}}{{name}}{{^}}{{none}}{{/people}}"
        context = {'none': "No people"}
        result = u"No people"

        self.assertRender(template, context, result)

    def test_block_inverted_sections_with_empty_arrays(self):
        template = u"{{#people}}{{name}}{{^}}{{none}}{{/people}}"
        context = {
            'none': "No people",
            'people': []
        }
        result = u"No people"

        self.assertRender(template, context, result)

    def test_block_helper_inverted_sections(self):
        def list(this, options, context):
            if len(context):
                out = "<ul>"
                for thing in context:
                    out += "<li>"
                    out += str_class(options['fn'](thing))
                    out += "</li>"
                out += "</ul>"
                return out
            else:
                return "<p>" + str_class(options['inverse'](this)) + "</p>"

        helpers = {'list': list}

        template = u"{{#list people}}{{name}}{{^}}<em>Nobody's here</em>{{/list}}"
        context = {
            'people': [
                {'name': "Alan"},
                {'name': "Yehuda"}
            ]
        }
        result = u"<ul><li>Alan</li><li>Yehuda</li></ul>"

        self.assertRender(template, context, result, helpers)

        context = {
            'people': []
        }
        result = u"<p><em>Nobody's here</em></p>"

        self.assertRender(template, context, result, helpers)

        template = u"{{#list people}}{{name}}{{else}}<em>Nobody's here</em>{{/list}}"
        context = {
            'people': [
                {'name': "Alan"},
                {'name': "Yehuda"}
            ]
        }
        result = u"<ul><li>Alan</li><li>Yehuda</li></ul>"

        self.assertRender(template, context, result, helpers)

        context = {
            'people': []
        }
        result = u"<p><em>Nobody's here</em></p>"

        self.assertRender(template, context, result, helpers)

        template = u"{{#list people}}Hello{{^}}{{message}}{{/list}}"
        context = {
            'people': [],
            'message': "Nobody's here"
        }
        result = u"<p>Nobody&#x27;s here</p>"

        self.assertRender(template, context, result, helpers)

    def test_providing_a_helpers_hash(self):
        helpers = {'world': "world"}

        template = u"Goodbye {{cruel}} {{world}}!"
        context = {
            'cruel': "cruel"
        }
        result = u"Goodbye cruel world!"

        self.assertRender(template, context, result, helpers)

        template = u"Goodbye {{#iter}}{{cruel}} {{world}}{{/iter}}!"
        context = {
            'iter': [
                {'cruel': "cruel"}
            ]
        }
        result = u"Goodbye cruel world!"

        self.assertRender(template, context, result, helpers)

    def test_in_cases_of_conflict_helpers_before_context(self):
        helpers = {'lookup': 'helpers'}
        template = u"{{lookup}}"
        context = {
            'lookup': 'Explicit'
        }
        result = u"helpers"

        self.assertRender(template, context, result, helpers)

        helpers = {'lookup': 'helpers'}
        template = u"{{{lookup}}}"
        context = {
            'lookup': 'Explicit'
        }
        result = u"helpers"

        self.assertRender(template, context, result, helpers)

        helpers = {'lookup': [{}]}
        template = u"{{#lookup}}Explicit{{/lookup}}"
        context = {
            'lookup': []
        }
        result = u"Explicit"

        self.assertRender(template, context, result, helpers)

    def test_the_helpers_hash_is_available_is_nested_contexts(self):
        helpers = {'helper': 'helper'}

        template = u"{{#outer}}{{#inner}}{{helper}}{{/inner}}{{/outer}}"
        context = {'outer': {'inner': {'unused': []}}}
        result = u"helper"

        self.assertRender(template, context, result, helpers)

    def test_basic_partials(self):
        partials = {
            'dude': u"{{name}} ({{url}}) "
        }

        template = u"Dudes: {{#dudes}}{{> dude}}{{/dudes}}"
        context = {
            'dudes': [
                {
                    'name': "Yehuda",
                    'url': "http://yehuda"
                },
                {
                    'name': "Alan",
                    'url': "http://alan"
                }
            ]
        }
        result = u"Dudes: Yehuda (http://yehuda) Alan (http://alan) "

        self.assertRender(template, context, result, None, partials)

    def test_partials_with_context(self):
        partials = {
            'dude': u"{{#this}}{{name}} ({{url}}) {{/this}}"
        }

        template = u"Dudes: {{>dude dudes}}"
        context = {
            'dudes': [
                {
                    'name': "Yehuda",
                    'url': "http://yehuda"
                },
                {
                    'name': "Alan",
                    'url': "http://alan"
                }
            ]
        }
        result = u"Dudes: Yehuda (http://yehuda) Alan (http://alan) "

        self.assertRender(template, context, result, None, partials)

    def test_partials_too_many_args(self):
        partials = {
            'dude': u"{{#this}}{{name}} ({{url}}) {{/this}}"
        }

        template = u'Dudes: {{>dude dudes "extra"}}'
        context = {
            'dudes': [
                {
                    'name': "Yehuda",
                    'url': "http://yehuda"
                },
                {
                    'name': "Alan",
                    'url': "http://alan"
                }
            ]
        }

        self.assertRaises(PybarsError, render, template, context, partials=partials)

    def test_partials_kwargs(self):
        partials = {
            'dude': u"{{name}} ({{url}}) "
        }

        template = u'Dudes: {{#dudes}}{{>dude url="http://example"}}{{/dudes}}'
        context = {
            'dudes': [
                {
                    'name': "Yehuda",
                    'url': "http://yehuda"
                },
                {
                    'name': "Alan",
                    'url': "http://alan"
                }
            ]
        }
        result = u"Dudes: Yehuda (http://example) Alan (http://example) "

        self.assertRender(template, context, result, None, partials)

    def test_partial_in_a_partial(self):
        partials = {
            'dude': u"{{name}} {{> url}} ",
            'url': u"<a href='{{url}}'>{{url}}</a>"
        }

        template = u"Dudes: {{#dudes}}{{>dude}}{{/dudes}}"
        context = {
            'dudes': [
                {
                    'name': "Yehuda",
                    'url': "http://yehuda"
                },
                {
                    'name': "Alan",
                    'url': "http://alan"
                }
            ]
        }
        result = (
            "Dudes: Yehuda <a href='http://yehuda'>http://yehuda</a>"
            " Alan <a href='http://alan'>http://alan</a> "
        )

        self.assertRender(template, context, result, None, partials)

    def test_rendering_undefined_partial_throws_an_exception(self):
        template = u"{{> whatever}}"
        context = {}

        self.assertRaises(PybarsError, render, template, context)

    def test_root_nested_partial(self):
        partials = {
            'dude': u"{{name}} {{> url}} ",
            'url': u"<a href='{{url}}' target='{{@root.target}}'>{{url}}</a>"
        }

        template = u"Dudes: {{#dudes}}{{>dude}}{{/dudes}}"
        context = {
            'target': '_blank',
            'dudes': [
                {
                    'name': "Yehuda",
                    'url': "http://yehuda"
                },
                {
                    'name': "Alan",
                    'url': "http://alan"
                }
            ]
        }
        result = (
            "Dudes: Yehuda <a href='http://yehuda' target='_blank'>http://yehuda</a>"
            " Alan <a href='http://alan' target='_blank'>http://alan</a> "
        )

        self.assertRender(template, context, result, None, partials)

    def test_GH_14_a_partial_preceding_a_selector(self):
        partials = {
            'dude': u"{{name}}"
        }

        template = u"Dudes: {{>dude}} {{another_dude}}"
        context = {
            'name': "Jeepers",
            'another_dude': "Creepers"
        }
        result = u"Dudes: Jeepers Creepers"

        self.assertRender(template, context, result, None, partials)

    def test_partials_with_literal_paths(self):
        partials = {
            'dude': u"{{name}}"
        }

        template = u"Dudes: {{> [dude]}}"
        context = {
            'name': "Jeepers",
            'another_dude': "Creepers"
        }
        result = u"Dudes: Jeepers"

        self.assertRender(template, context, result, None, partials)

    def test_partials_with_string(self):
        partials = {
            '+404/asdf?.bar': u"{{name}}"
        }

        template = u'Dudes: {{> "+404/asdf?.bar"}}'
        context = {
            'name': "Jeepers",
            'another_dude': "Creepers"
        }
        result = u"Dudes: Jeepers"

        self.assertRender(template, context, result, None, partials)

    def test_dynamic_partials(self):
        def helper_partial(this):
            return "dude"

        helpers = {
            'partial': helper_partial
        }

        partials = {
            "dude": u"{{name}} ({{url}}) ",
        }

        template = u"Dudes: {{#dudes}}{{> (partial)}}{{/dudes}}"
        context = {
            "dudes": [{"name": "Yehuda", "url": "http://yehuda"}, {"name": "Alan", "url": "http://alan"}]
        }
        result = u"Dudes: Yehuda (http://yehuda) Alan (http://alan) "

        self.assertRender(template, context, result, helpers, partials)

    def test_dynamic_partials_with_explicit_scope(self):
        def helper_partial(this):
            return "dude"

        helpers = {
            'partial': helper_partial
        }

        partials = {
            "dude": u"{{note}}",
        }

        template = u"Dudes: {{#dudes}}{{> (partial) @root.joke}} {{/dudes}}"
        context = {
            "dudes": [{"name": "Yehuda", "url": "http://yehuda"}, {"name": "Alan", "url": "http://alan"}],
            "joke": {"note": "explicit scope for partial"},
        }
        result = u"Dudes: explicit scope for partial explicit scope for partial "

        self.assertRender(template, context, result, helpers, partials)

    def test_failing_dynamic_partials(self):
        def helper_partial(this):
            return "missing"

        helpers = {
            'partial': helper_partial
        }

        partials = {
            "dude": u"{{name}} ({{url}}) ",
        }

        template = u"Dudes: {{#dudes}}{{> (partial)}}{{/dudes}}"
        context = {
            "dudes": [{"name": "Yehuda", "url": "http://yehuda"}, {"name": "Alan", "url": "http://alan"}]
        }
        result = u"Dudes: Yehuda (http://yehuda) Alan (http://alan) "

        error = 'The partial missing could not be found'

        self.assertRender(template, context, result, helpers=helpers, partials=partials, error=error)

    def test_dynamic_partials_name(self):
        def helper_whichPartial(this):
            return "partialOne"

        helpers = {
            'whichPartial': helper_whichPartial
        }

        partials = {
            "partialOne": u"1 1 1",
            "partialTwo": u"2 2 2",
        }

        template = u"It is {{> (whichPartial)}} items"
        context = {}
        result = u"It is 1 1 1 items"

        self.assertRender(template, context, result, helpers, partials)

    def test_dynamic_partials_with_params(self):

        def helper_whichPartialParametrized(this, suffix):
            return "partial" + suffix

        helpers = {
            'whichPartial': helper_whichPartialParametrized
        }

        partials = {
            "partialOne": u"1 1 1",
            "partialTwo": u"2 2 2",
        }

        context = {
            "suffix": "Two"
        }

        template = u"It is literal call: {{> (whichPartial 'One')}}. And from context: {{> (whichPartial suffix)}}"
        result = u"It is literal call: 1 1 1. And from context: 2 2 2"
        self.assertRender(template, context, result, helpers, partials)

    def test_simple_literals_work(self):

        def hello(this, param, times, bool1, bool2):
            self.assertEqual(True, bool1)
            self.assertEqual(False, bool2)
            self.assertEqual(12, times)
            return ("Hello " + param + " " + str_class(times) + " times: "
                + str_class(bool1) + " " + str_class(bool2))

        helpers = {'hello': hello}

        template = u'Message: {{hello "world" 12 true false}}'
        context = {}
        result = u"Message: Hello world 12 times: True False"

        self.assertRender(template, context, result, helpers)

    def test_true(self):
        template = u"{{var}}"
        context = {
            'var': True
        }
        result = u"true"

        self.assertRender(template, context, result)

    def test_true_unescaped(self):
        template = u"{{{var}}}"
        context = {
            'var': True
        }
        result = u"true"

        self.assertRender(template, context, result)

    def test_false(self):
        template = u"{{var}}"
        context = {
            'var': False
        }
        result = u"false"

        self.assertRender(template, context, result)

    def test_false_unescaped(self):
        template = u"{{{var}}}"
        context = {
            'var': False
        }
        result = u"false"

        self.assertRender(template, context, result)

    def test_none(self):
        template = u"{{var}}"
        context = {
            'var': None
        }
        result = u""

        self.assertRender(template, context, result)

    def test_none_unescaped(self):
        template = u"{{{var}}}"
        context = {
            'var': None
        }
        result = u""

        self.assertRender(template, context, result)

    def test_null(self):

        def hello(this, param):
            return "Hello " + ('' if param is None else param)

        helpers = {'hello': hello}

        template = u"Message: {{{hello null}}}"
        context = {}
        result = u"Message: Hello "

        self.assertRender(template, context, result, helpers)

    def test_undefined(self):

        def hello(this, param):
            return "Hello " + ('' if param is None else param)

        helpers = {'hello': hello}

        template = u"Message: {{{hello undefined}}}"
        context = {}
        result = u"Message: Hello "

        self.assertRender(template, context, result, helpers)

    def test_block_tag_whitespace(self):
        template = u"  {{#if var}}\n    {{var}}\n  {{/if}}"
        context = {
            'var': 'Hello'
        }
        result = u"    Hello"

        self.assertRender(template, context, result)

        template = u"{{#if var}}    \n    {{var}}\n  {{/if}}    "

        self.assertRender(template, context, result)

        template = u"{{#if var}}\n    {{var}}\n{{/if}}    "

        self.assertRender(template, context, result)

        template = u"{{#if var}}\n    {{var}}\n{{/if}}"

        self.assertRender(template, context, result)

        template = u"{{#if var}}    \r\n    {{var}}\r\n  {{/if}}    "

        self.assertRender(template, context, result)

        template = u"\n{{#if var}}\n    {{var}}\n{{/if}}"
        result = u"\n    Hello"

        self.assertRender(template, context, result)

    def test_using_a_quote_in_the_middle_of_a_parameter_raises_an_error(self):
        template = u'Message: {{hello wo"a"}}'
        context = None

        self.assertRaises(PybarsError, render, template, context)

    def test_escaping_a_String_is_possible(self):

        def hello(this, param):
            return "Hello " + param

        helpers = {'hello': hello}

        template = u'Message: {{{hello "\\"world\\""}}}'
        context = {}
        result = u"Message: Hello \"world\""

        self.assertRender(template, context, result, helpers)

    def test_it_works_with_single_quote_marks(self):

        def hello(this, param):
            return "Hello " + param

        helpers = {'hello': hello}

        template = u"Message: {{{hello 'Alan\\\'s world'}}}"
        context = {}
        result = u"Message: Hello Alan's world"

        self.assertRender(template, context, result, helpers)

    def test_simple_multi_params_work(self):

        def goodbye(this, cruel, world):
            return "Goodbye " + cruel + " " + world

        helpers = {'goodbye': goodbye}

        template = u'Message: {{goodbye cruel world}}'
        context = {
            'cruel': "cruel",
            'world': "world"
        }
        result = u"Message: Goodbye cruel world"

        self.assertRender(template, context, result, helpers)

    def test_block_multi_params_work(self):

        def goodbye(this, options, cruel, world):
            return options['fn'](
                {'greeting': "Goodbye", 'adj': cruel, 'noun': world})

        helpers = {'goodbye': goodbye}

        template = (
            u'Message: {{#goodbye cruel world}}'
            u'{{greeting}} {{adj}} {{noun}}{{/goodbye}}'
        )
        context = {
            'cruel': "cruel",
            'world': "world"
        }
        result = u"Message: Goodbye cruel world"

        self.assertRender(template, context, result, helpers)

    def test_constructing_a_safestring_from_a_string_and_checking_its_type(self):
        reference = "testing 1, 2, 3"
        instance = strlist([reference])
        self.assertIsInstance(instance, strlist)
        self.assertEqual(str_class(reference), str_class(instance))

    def test_if_a_context_is_not_found_helperMissing_is_used(self):

        def link_to(this, helpername, context):
            if helpername == 'link_to':
                return strlist(("<a>", context, "</a>"))

        helpers = {'helperMissing': link_to}

        template = u"{{hello}} {{link_to world}}"
        context = {
            'hello': "Hello",
            'world': "world"
        }
        result = u"Hello <a>world</a>"

        self.assertRender(template, context, result, helpers)

    def test_Known_helper_should_render_helper(self):
        helpers = {'hello': lambda this: "foo"}

        template = u"{{hello}}"
        context = {}
        result = u"foo"

        self.assertRender(template, context, result, helpers)

    def test_Unknown_helper_in_knownHelpers_only_mode_should_be_passed_as_undefined(self):
        helpers = {
            'typeof': lambda this, arg: str_class(type(arg)),
            'hello': lambda this: "foo"
        }

        template = u"{{{typeof hello}}}"
        context = {}
        result = u"<type 'NoneType'>" if sys.version_info < (3,) else "<class 'NoneType'>"

        self.assertRender(template, context, result, helpers, knownHelpers=set(['typeof']), knownHelpersOnly=True)

    def test_Builtin_helpers_available_in_knownHelpers_only_mode(self):
        template = u"{{#unless foo}}bar{{/unless}}"
        context = {}
        result = u"bar"

        self.assertRender(template, context, result, knownHelpersOnly=True)

    def test_Field_lookup_works_in_knownHelpers_only_mode(self):
        template = u"{{foo}}"
        context = {
            'foo': 'bar'
        }
        result = u"bar"

        self.assertRender(template, context, result, knownHelpersOnly=True)

    def test_Conditional_blocks_work_in_knownHelpers_only_mode(self):
        template = u"{{#foo}}bar{{/foo}}"
        context = {
            'foo': 'baz'
        }
        result = u"bar"

        self.assertRender(template, context, result, knownHelpersOnly=True)

    def test_Invert_blocks_work_in_knownHelpers_only_mode(self):
        template = u"{{^foo}}bar{{/foo}}"
        context = {
            'foo': False
        }
        result = u"bar"

        self.assertRender(template, context, result, knownHelpersOnly=True)

    def test_lambdas_are_resolved_by_blockHelperMissing_not_handlebars_proper(self):
        # Probably should be called 'lambdas in the context are called as
        # though for a simple block' - it wants to check moustache
        # compatibility which allows all block stuff to be overridden via
        # blockHelperMissing
        template = u"{{#truthy}}yep{{/truthy}}"
        context = {
            'truthy': lambda this: True
        }
        result = u"yep"

        self.assertRender(template, context, result)

    def test_default_helperMissing_no_params(self):
        template = u"a{{missing}}b"
        context = {}
        result = u"ab"

        self.assertRender(template, context, result)

    def test_default_helperMissing_with_param(self):
        template = u"a{{missing something}}b"
        context = {}

        self.assertRaises(PybarsError, render, template, context)

    def test_with(self):
        template = u"{{#with person}}{{first}} {{last}}{{/with}}"
        context = {
            'person': {
                'first': "Alan",
                'last': "Johnson"
            }
        }
        result = u"Alan Johnson"

        self.assertRender(template, context, result)

    def test_if(self):
        template = u"{{#if goodbye}}GOODBYE {{/if}}cruel {{world}}!"

        context = {
            'goodbye': True,
            'world': "world"
        }
        result = u"GOODBYE cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbye': 'dummy',
            'world': "world"
        }
        result = u"GOODBYE cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbye': False,
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

        context = {
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbye': ['foo'],
            'world': "world"
        }
        result = u"GOODBYE cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbye': [],
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

    def test_if_else(self):
        template = u"{{#if goodbye}}GOODBYE{{else}}Hello{{/if}} cruel {{world}}!"
        context = {
            'goodbye': False,
            'world': "world"
        }
        result = u"Hello cruel world!"

        self.assertRender(template, context, result)

        template = u"{{^if goodbye}}Hello{{else}}GOODBYE{{/if}}"

        self.assertRender(template, {}, u"Hello")
        self.assertRender(template, {'goodbye': True}, u"GOODBYE")
        self.assertRender(template, {'goodbye': "goodbye"}, u"GOODBYE")
        self.assertRender(template, {'goodbye': False}, u"Hello")
        self.assertRender(template, {'hello': 'hello'}, u"Hello")

    def test_if_with_function_argument(self):
        template = u"{{#if goodbye}}GOODBYE {{/if}}cruel {{world}}!"

        context = {
            'goodbye': lambda this: True,
            'world': "world"
        }
        result = u"GOODBYE cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbye': lambda this: this['world'],
            'world': "world"
        }
        result = u"GOODBYE cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbye': lambda this: False,
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

        context = {
            'goodbye': lambda this: None,
            'world': "world"
        }
        result = u"cruel world!"

        self.assertRender(template, context, result)

    def test_resolve_with_attrs(self):

        class TestAttr():

            @property
            def text(self):
                return 'Hello'

        class TestGet():

            def get(self, name):
                return {'text': 'Hi'}.get(name)

        template = u"{{#each .}}{{test.text}}! {{/each}}"
        context = [
            {'test': TestAttr()},
            {'test': TestGet()},
            {'test': {'text': 'Goodbye'}}
        ]
        result = u"Hello! Hi! Goodbye! "

        self.assertRender(template, context, result)

    def test_list_context(self):
        template = u"{{#each .}}{{#each .}}{{text}}! {{/each}}cruel world!{{/each}}"
        context = [
            [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ]
        ]
        result = u"goodbye! Goodbye! GOODBYE! cruel world!"

        self.assertRender(template, context, result)

    def test_context_with_attrs(self):

        class TestContext():

            @property
            def text(self):
                return 'Goodbye'

        template = u"{{#each .}}{{text}}! {{/each}}cruel world!"
        context = [
            TestContext()
        ]
        result = u"Goodbye! cruel world!"

        self.assertRender(template, context, result)

    def test_each(self):
        template = u"{{#each goodbyes}}{{text}}! {{/each}}cruel {{world}}!"

        context = {
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ],
            'world': "world"
        }
        result = u"goodbye! Goodbye! GOODBYE! cruel world!"

        self.assertRender(template, context, result)

        context = {'goodbyes': [], 'world': "world"}
        result = u"cruel world!"

        self.assertRender(template, context, result)

    def test_each_this(self):
        helpers = {
            'capitalize': lambda this, value: value.upper()
        }

        template = u"{{#each name}}{{capitalize this}} {{/each}}"
        context = {
            'name': [
                'John',
                'James'
            ]
        }
        result = u"JOHN JAMES "

        self.assertRender(template, context, result, helpers)

    def test_each_of_None(self):
        template = u"Goodbye {{#each things}}cruel{{/each}} world!"
        context = {
            'things': None
        }
        result = u"Goodbye  world!"

        self.assertRender(template, context, result)

        template = u"Goodbye {{^each things}}cruel{{/each}} world!"
        context = {
            'things': None
        }
        result = u"Goodbye cruel world!"

        self.assertRender(template, context, result)

    def test_each_of_empty_list(self):
        template = u"Goodbye {{#each things}}happy {{^}}cruel {{/each}}world!"
        context = {
            'things': []
        }
        result = u"Goodbye cruel world!"

        self.assertRender(template, context, result)

    def test_each_of_non_empty_list(self):
        template = u"Goodbye {{#each things}}cruel{{/each}} world!"
        context = {
            'things': ['thing1', 'thing2']
        }
        result = u"Goodbye cruelcruel world!"

        self.assertRender(template, context, result)

        template = u"Goodbye {{^each things}}cruel{{/each}} world!"
        result = u"Goodbye  world!"

        self.assertRender(template, context, result)

    def test_each_of_truthy_non_iterable_object(self):
        template = u"Goodbye {{#each things}}happy {{^}}cruel {{/each}}world!"
        context = {
            'things': True
        }
        result = u"Goodbye cruel world!"

        self.assertRender(template, context, result)

    def test_each_with_object_and_key(self):
        template = u"{{#each goodbyes}}{{@key}}. {{text}}! {{/each}}cruel {{world}}!"
        context = {
            'goodbyes': {
                "<b>#1</b>": {
                    'text': "goodbye"
                },
                2: {
                    'text': "GOODBYE"
                }
            },
            'world': "world"
        }

        self.assertIn(
            render(template, context),
            # Depending on iteration order, one will come before the other.
            (
                "&lt;b&gt;#1&lt;/b&gt;. goodbye! 2. GOODBYE! cruel world!",
                "2. GOODBYE! &lt;b&gt;#1&lt;/b&gt;. goodbye! cruel world!"
            )
        )

    def test_each_with_index(self):
        template = u"{{#each goodbyes}}{{@index}}. {{text}}! {{/each}}cruel {{world}}!"
        context = {
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ],
            'world': "world"
        }
        result = u"0. goodbye! 1. Goodbye! 2. GOODBYE! cruel world!"

        self.assertRender(template, context, result)

    def test_each_with_nested_index(self):
        template = u"{{#each goodbyes}}{{@index}}. {{text}}! {{#each ../goodbyes}}{{@index}} {{/each}}After {{@index}} {{/each}}{{@index}}cruel {{world}}!"
        context = {
            'goodbyes': [
                {'text': "goodbye"},
                {'text': "Goodbye"},
                {'text': "GOODBYE"}
            ],
            'world': "world"
        }
        result = u"0. goodbye! 0 1 2 After 0 1. Goodbye! 0 1 2 After 1 2. GOODBYE! 0 1 2 After 2 cruel world!"

        self.assertRender(template, context, result)

    def test_each_with_parent_index(self):
        template = u"{{#each people}}{{#each foods}}{{../name}}({{@../index}}) likes {{name}}({{@index}}), {{/each}}{{/each}}"
        context = {
            'people': [
                {
                    'name': 'John',
                    'foods': [
                        {'name': 'apples'},
                        {'name': 'pears'}
                    ]
                },
                {
                    'name': 'Jane',
                    'foods': [
                        {'name': 'grapes'},
                        {'name': 'pineapple'}
                    ]
                }
            ]
        }
        result = u"John(0) likes apples(0), John(0) likes pears(1), Jane(1) likes grapes(0), Jane(1) likes pineapple(1), "

        self.assertRender(template, context, result)

    def test_log(self):
        template = u"{{log blah}}"
        context = {
            'blah': "whee"
        }
        result = ''

        log = []
        original_log = pybars.log
        pybars.log = log.append

        self.assertRender(template, context, result)
        self.assertEqual(["whee"], log)

        pybars.log = original_log

    def test_log_underlying_function(self):
        # log implementation and test are just stubs
        template = u"{{log '123'}}"
        result = ''
        self.assertRender(template, {}, result)

    def test_overriding_property_lookup(self):
        pass
        # Empty upstream

    # ... in data ... skipped

    def test_helpers_take_precedence_over_same_named_context_properties(self):
        helpers = {
            'goodbye': lambda this: this['goodbye'].upper()
        }

        template = u"{{goodbye}} {{cruel world}}"
        context = {
            'goodbye': "goodbye",
            'cruel': lambda this, world: "cruel " + world.upper(),
            'world': "world"
        }
        result = u"GOODBYE cruel WORLD"

        self.assertRender(template, context, result, helpers)

    def test_block_helpers_take_precedence_over_same_named_context_properties(self):

        def goodbye(this, options):
            return strlist([this['goodbye'].upper()]) + options['fn'](this)

        helpers = {'goodbye': goodbye}

        template = u"{{#goodbye}} {{cruel world}}{{/goodbye}}"
        context = {
            'goodbye': "goodbye",
            'cruel': lambda this, world: "cruel " + world.upper(),
            'world': "world"
        }
        result = u"GOODBYE cruel WORLD"

        self.assertRender(template, context, result, helpers)

    def test_Scoped_names_take_precedence_over_helpers(self):
        helpers = {
            'goodbye': lambda this: this['goodbye'].upper()
        }

        template = u"{{this.goodbye}} {{cruel world}} {{cruel this.goodbye}}"
        context = {
            'goodbye': "goodbye",
            'cruel': lambda this, world: "cruel " + world.upper(),
            'world': "world"
        }
        result = u"goodbye cruel WORLD cruel GOODBYE"

        self.assertRender(template, context, result, helpers)

    def test_Scoped_names_take_precedence_over_block_helpers(self):

        def goodbye(this, options):
            return strlist([this['goodbye'].upper()]) + options['fn'](this)

        helpers = {'goodbye': goodbye}

        template = u"{{#goodbye}} {{cruel world}}{{/goodbye}} {{this.goodbye}}"
        context = {
            'goodbye': "goodbye",
            'cruel': lambda this, world: "cruel " + world.upper(),
            'world': "world"
        }
        result = u"GOODBYE cruel WORLD goodbye"

        self.assertRender(template, context, result, helpers)

    def test_helpers_can_take_an_optional_hash(self):
        # Note: the order is a rotation on the template order to avoid *args
        # processing generating a false pass
        def goodbye(this, times, cruel, world):
            return "GOODBYE " + cruel + " " + world + " " + str(times) + " TIMES"

        helpers = {'goodbye': goodbye}

        template = u'{{goodbye cruel="CRUEL" world="WORLD" times=12}}'
        context = {}
        result = u"GOODBYE CRUEL WORLD 12 TIMES"

        self.assertRender(template, context, result, helpers)

    def test_helpers_can_take_an_optional_hash_with_booleans(self):

        def goodbye(this, cruel, world, _print):
            if _print is True:
                return "GOODBYE " + cruel + " " + world
            elif _print is False:
                return "NOT PRINTING"
            else:
                return "THIS SHOULD NOT HAPPEN"

        helpers = {'goodbye': goodbye}

        template = u'{{goodbye cruel="CRUEL" world="WORLD" _print=true}}'
        context = {}
        result = u"GOODBYE CRUEL WORLD"

        self.assertRender(template, context, result, helpers)

        template = u'{{goodbye cruel="CRUEL" world="WORLD" _print=false}}'
        context = {}
        result = u"NOT PRINTING"

        self.assertRender(template, context, result, helpers)

    def test_block_helpers_can_take_an_optional_hash(self):

        def goodbye(this, options, times, cruel):
            return "GOODBYE " + cruel + " " + str_class(options['fn'](this)) + " " + str(times) + " TIMES"

        helpers = {'goodbye': goodbye}

        template = u'{{#goodbye cruel="CRUEL" times=12}}world{{/goodbye}}'
        context = {}
        result = u"GOODBYE CRUEL world 12 TIMES"

        self.assertRender(template, context, result, helpers)

    def test_block_helpers_can_take_an_optional_hash_with_booleans(self):

        def goodbye(this, options, cruel, _print):
            if _print is True:
                return "GOODBYE " + cruel + " " + str_class(options['fn'](this))
            elif _print is False:
                return "NOT PRINTING"
            else:
                return "THIS SHOULD NOT HAPPEN"

        helpers = {'goodbye': goodbye}

        template = u'{{#goodbye cruel="CRUEL" _print=true}}world{{/goodbye}}'
        context = {}
        result = u"GOODBYE CRUEL world"

        self.assertRender(template, context, result, helpers)

        template = u'{{#goodbye cruel="CRUEL" _print=false}}world{{/goodbye}}'
        context = {}
        result = u"NOT PRINTING"

        self.assertRender(template, context, result, helpers)

    def test_should_lookup_arbitrary_content(self):
        template = u'{{#each goodbyes}}{{lookup ../data .}}{{/each}}'
        context = {
            'goodbyes': [
                0,
                1
            ],
            'data': [
                'foo',
                'bar'
            ]
        }
        result = 'foobar'

        self.assertRender(template, context, result)

    def test_should_not_fail_on_undefined_value(self):
        template = u'{{#each goodbyes}}{{lookup ../bar .}}{{/each}}'
        context = {
            'goodbyes': [
                0,
                1
            ],
            'data': [
                'foo',
                'bar'
            ]
        }
        result = ''

        self.assertRender(template, context, result)

    def test_should_not_fail_on_unavailable_value(self):
        template = u'{{lookup thelist 3}}.{{lookup theobject "qux"}}.{{lookup thenumber 0}}'
        context = {
            'thelist': [
                'foo',
                'bar'
            ],
            'theobject': {
                'foo': 'bar'
            },
            'thenumber': 7
        }
        result = '..'

        self.assertRender(template, context, result)

    def test_should_lookup_content_by_special_variables(self):
        template = u'{{#each goodbyes}}{{lookup ../data @index}}{{/each}}'
        context = {
            'goodbyes': [
                0,
                1
            ],
            'data': [
                'foo',
                'bar'
            ]
        }
        result = 'foobar'

        self.assertRender(template, context, result)

    def test_cannot_read_property_of_undefined(self):
        template = u"{{#books}}{{title}}{{author.name}}{{/books}}"
        context = {
            "books": [
                {
                    "title": "The origin of species",
                    "author": {
                        "name": "Charles Darwin"
                    }
                },
                {
                    "title": "Lazarillo de Tormes"
                }
            ]
        }
        result = u"The origin of speciesCharles DarwinLazarillo de Tormes"

        self.assertRender(template, context, result)

    def test_inverted_sections_print_when_they_shouldnt(self):
        template = u"{{^set}}not set{{/set}} :: {{#set}}set{{/set}}"

        context = {}
        result = u"not set :: "

        self.assertRender(template, context, result)

        context = {
            'set': None
        }
        result = u"not set :: "

        self.assertRender(template, context, result)

        context = {
            'set': False
        }
        result = u"not set :: "

        self.assertRender(template, context, result)

        context = {
            'set': True
        }
        result = u" :: set"

        self.assertRender(template, context, result)

    def test_Mustache_man_page(self):
        template = (
            u"Hello {{name}}. You have just won ${{value}}!"
            u"{{#in_ca}} Well, ${{taxed_value}}, after taxes.{{/in_ca}}"
        )
        context = {
            "name": "Chris",
            "value": 10000,
            # Note that the int here is not needed in JS because JS doesn't
            # have ints and floats.
            "taxed_value": int(10000 - (10000 * 0.4)),
            "in_ca": True
        }
        result = u"Hello Chris. You have just won $10000! Well, $6000, after taxes."

        self.assertRender(template, context, result)

    def test_GH_158__Using_array_index_twice_breaks_the_template(self):
        template = u"{{arr.[0]}}, {{arr.[1]}}"
        context = {
            "arr": [
                1,
                2
            ]
        }
        result = u"1, 2"

        self.assertRender(template, context, result)

    def test_bug_reported_by__fat_where_lambdas_weren_t_being_properly_resolved(self):
        template = u"<strong>This is a slightly more complicated {{thing}}.</strong>.\n{{! Just ignore this business. }}\nCheck this out:\n{{#hasThings}}\n<ul>\n{{#things}}\n<li class={{className}}>{{word}}</li>\n{{/things}}</ul>.\n{{/hasThings}}\n{{^hasThings}}\n\n<small>Nothing to check out...</small>\n{{/hasThings}}"  # noqa: E501
        context = {
            'thing': lambda this: "blah",
            'things': [
                {
                    'className': "one",
                    'word': "@fat"
                },
                {
                    'className': "two",
                    'word': "@dhg"
                },
                {
                    'className': "three",
                    'word': "@sayrer"
                }
            ],
            'hasThings': lambda this: True
        }
        result = u"<strong>This is a slightly more complicated blah.</strong>.\n\nCheck this out:\n\n<ul>\n\n<li class=one>@fat</li>\n\n<li class=two>@dhg</li>\n\n<li class=three>@sayrer</li>\n</ul>.\n\n"    # noqa: E501

        self.assertRender(template, context, result)

    def test_invalid_python_identifiers_cannot_be_used_as_keyword_arguments(self):
        template = u'{{foo 0x="bar"}}'
        context = {}
        result = None
        error = 'Error at character 7 of line 1 near 0x="bar"}}'

        self.assertRender(template, context, result, error=error)

    def test_backslash_does_not_normally_escape_text(self):
        helpers = {
            'echo': lambda this, arg: arg
        }

        template = u'{{echo "\\x"}}'
        context = {}
        result = '\\x'

        self.assertRender(template, context, result, helpers)

    def test_backslash_only_escapes_quote(self):
        helpers = {
            'echo': lambda this, arg: arg
        }

        # If the parser does not know to escape the backslash but does know to
        # escape the quote, it will end up with something like the following
        # in our generated rendering code:
        #
        #     value = value(child_scope, "\\"")
        #
        # Which will raise a SyntaxError.
        template = u'{{echo "\\\\""}}'
        context = {}
        result = '\\&quot;'

        self.assertRender(template, context, result, helpers)

    def test_newlines_in_string_litereals(self):
        helpers = {
            'echo': lambda this, arg: arg
        }

        template = u'{{echo "Hello,\nWorld!"}}'
        context = {}
        result = 'Hello,\nWorld!'

        self.assertRender(template, context, result, helpers)

    def test_code_injection(self):
        helpers = {
            'echo': lambda this, arg: arg
        }

        # If esape sequences are not dealt with properly, we are able to run
        # arbitrary Python code.
        template = u'{{echo "\\\\")\n\n        raise AssertionError(\'Code Injected!\')\n#"}}'
        context = {}
        result = '\\&quot;)\n\n        raise AssertionError(&#x27;Code Injected!&#x27;)\n#'

        self.assertRender(template, context, result, helpers)

    def test_precompile(self):
        try:
            template = u"Goodbye\n{{cruel}}\n{{world}}!"
            context = {
                'cruel': "cruel",
                'world': "world"
            }
            result = u"Goodbye\ncruel\nworld!"

            compiler = Compiler()
            code = compiler.precompile(template)

            with open('test_precompile.py', 'w') as f:
                f.write(code)

            import test_precompile

            self.assertEqual(result, str(test_precompile.render(context)))

        finally:
            if os.path.exists('test_precompile.py'):
                os.unlink('test_precompile.py')

    def test_attribute_precedence(self):
        class MyDict(dict):
            world = "goodbye"

        template = u"{{hello.world}}"
        context = {
            "hello": MyDict({"world": "hello"})
        }
        result = u"hello"

        context2 = {
            "hello": MyDict()
        }
        result2 = u"goodbye"

        self.assertRender(template, context, result)
        self.assertRender(template, context2, result2)

    def test_raw_block(self):
        template = u"{{{{raw}}}}{{escaped}}{{{{/raw}}}}"
        context = {}
        result = u"{{escaped}}"
        self.assertRender(template, context, result)

    def test_raw_block_in_block(self):
        template = u"{{#valid}}{{{{raw}}}}{{escaped}}{{{{/raw}}}}{{/valid}}"
        context = {
            "valid": True
        }
        result = u"{{escaped}}"
        self.assertRender(template, context, result)

    def test_raw_block_in_inverted_block(self):
        template = u"{{^valid}}{{{{raw}}}}{{escaped}}{{{{/raw}}}}{{/valid}}"
        context = {
            "valid": False
        }
        result = u"{{escaped}}"
        self.assertRender(template, context, result)

    def test_raw_block_with_spaces(self):
        template = u"this is a{{{{raw}}}} {{ .raw.block }}! {{{{/raw}}}}"
        context = {
            "valid": True
        }
        result = u"this is a {{ .raw.block }}! "
        self.assertRender(template, context, result)

    def test_raw_block_with_helper_that_gets_raw_content(self):
        template = u"{{{{raw}}}} {{test}} {{{{/raw}}}}"
        context = {
            "test": "hello"
        }
        helpers = {
            "raw": lambda this, options: options['fn'](this)
        }
        result = u" {{test}} "
        self.assertRender(template, context, result, helpers)

    def test_raw_block_with_helper_that_takes_args(self):
        template = u"{{{{raw \"sky\" \"is\" \"blue\"}}}}the {{{{/raw}}}}"
        context = {
            "test": u"hello"
        }
        helpers = {
            "raw": lambda this, options, a, b, c: options['fn'](this) + ' '.join([a, b, c])
        }
        result = u"the sky is blue"
        self.assertRender(template, context, result, helpers)

    def test_raw_block_with_helper_that_takes_kwargs(self):
        template1 = u"{{{{underline style=\"dotted\" width=18}}}} {{ Book Title }} {{{{/underline}}}}"
        template2 = u"{{{{underline}}}} {{ Book Title }} {{{{/underline}}}}"
        context = {}

        def underline(this, options, style=None, width=10):
            pattern = u'.' if style == 'dotted' else u'-'
            return options['fn'](this) + u"\n" + pattern * width

        helpers = {
            "underline": underline
        }
        result1 = u"\n".join([u" {{ Book Title }} ",
                             u".................."])
        result2 = u"\n".join([u" {{ Book Title }} ",
                             u"----------"])
        self.assertRender(template1, context, result1, helpers)
        self.assertRender(template2, context, result2, helpers)

    def test_nested_raw_block_with_helper_that_gets_raw_content(self):
        template = u"{{{{a}}}} {{{{b}}}} {{{{/b}}}} {{{{/a}}}}"
        context = {}
        helpers = {
            "a": lambda this, options: options['fn'](this)
        }
        result = u" {{{{b}}}} {{{{/b}}}} "
        self.assertRender(template, context, result, helpers)

    def test_nested_raw_blocks(self):
        template = u"{{{{a}}}} {{{{b}}}} {{{{/b}}}} {{{{/a}}}}"
        context = {}
        result = u" {{{{b}}}} {{{{/b}}}} "
        self.assertRender(template, context, result)

    def test_markdow_and_html_in_raw_block(self):
        template = u"{{{{markdown}}}}**HTML** <a href='#'>link</a>{{{{/markdown}}}}"
        context = {}
        result = u"**HTML** <a href='#'>link</a>"
        self.assertRender(template, context, result)

    def test_template(self):
        compiler = Compiler()

        # test precompiling a template
        text = u"Hi {{name}}!"
        context = {'name': u"Samira"}
        precompiled = compiler.precompile(text)
        template = compiler.template(precompiled)
        self.assertEqual(template(context), u"Hi Samira!")

        # test a different template
        text = u"Hello {{name}}!"
        context = {'name': u"Samira"}
        precompiled = compiler.precompile(text)
        template = compiler.template(precompiled)
        self.assertEqual(template(context), u"Hello Samira!")

        # test that compiling is not affected
        text = u"Hola {{name}}!"
        context = {'name': u"Samira"}
        self.assertRender(text, context, u"Hola Samira!")
