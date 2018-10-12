# Copyright (c) 2015 Will Bond, 2012 Canonical Ltd
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

"""Tests for the pybars compiler."""

try:
    str_class = unicode
except NameError:
    # Python 3 support
    str_class = str

import sys

from unittest import TestCase

from pybars import Compiler


def render(source, context, helpers=None, partials=None, knownHelpers=None,
           knownHelpersOnly=False):
    compiler = Compiler()
    template = compiler.compile(source)
    # For real use, partials is a dict of compiled templates; but for testing
    # we compile just-in-time.
    if not partials:
        real_partials = None
    else:
        real_partials = dict((key, compiler.compile(value))
            for key, value in list(partials.items()))
    return str_class(template(context, helpers=helpers, partials=real_partials))


class TestCompiler(TestCase):

    def test_import(self):
        import pybars
        pybars.Compiler

    def test_smoke(self):

        def _list(this, options, items):
            result = ['<ul>']
            for thing in items:
                result.append('<li>')
                result.extend(options['fn'](thing))
                result.append('</li>')
            result.append('</ul>')
            return result

        helpers = {u'list': _list}

        template = u"{{#list people}}{{firstName}} {{lastName}}{{/list}}"
        context = {
            'people': [
                {
                    'firstName': "Yehuda",
                    'lastName': "Katz"
                },
                {
                    'firstName': "Carl",
                    'lastName': "Lerche"
                },
                {
                    'firstName': "Alan",
                    'lastName': "Johnson"
                }
            ]
        }
        result = u"<ul><li>Yehuda Katz</li><li>Carl Lerche</li><li>Alan Johnson</li></ul>"

        self.assertEqual(result, render(template, context, helpers=helpers))

    def test_escapes(self):
        template = u"""\
            <div class="entry">
              <h1>{{title}}</h1>
              <div class="body">
                {{{body}}}
              </div>
            </div>
        """
        context = {
            'title': u"All about <p> Tags",
            'body': u"<p>This is a post about &lt;p&gt; tags</p>",
        }
        result = u"""\
            <div class="entry">
              <h1>All about &lt;p&gt; Tags</h1>
              <div class="body">
                <p>This is a post about &lt;p&gt; tags</p>
              </div>
            </div>
        """

        self.assertEqual(result, render(template, context))

    def test_segment_literal_notation(self):
        template = u"""{{foo.[bar baz]}}"""
        context = {
            'foo': {
                'bar baz': 'hello'
            }
        }
        result = u"""hello"""

        self.assertEqual(result, render(template, context))

    def test_compile_with_path(self):
        template = u"Hi {{name}}!"
        context = {
            'name': 'Ahmed'
        }
        result = u"Hi Ahmed!"
        path = '/project/widgets/templates'

        compiler = Compiler()

        # compile and check that speficified path is used
        self.assertEqual(result, compiler.compile(template, path=path)(context))
        self.assertTrue(sys.modules.get('pybars._templates._project_widgets_templates') is not None)

        # recompile and check that a new path is used
        self.assertEqual(result, compiler.compile(template, path=path)(context))
        self.assertTrue(sys.modules.get('pybars._templates._project_widgets_templates_1') is not None)
