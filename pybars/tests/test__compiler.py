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

"""Tests for the pybars compiler."""

from testtools import TestCase

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
            for key, value in partials.items())
    return unicode(template(context, helpers=helpers, partials=real_partials))


class TestCompiler(TestCase):
    
    def test_import(self):
        from pybars import Compiler

    def test_smoke(self):
        compiler = Compiler()
        def _list(this, options, items):
            result = ['<ul>']
            for thing in items:
                result.append('<li>')
                result.extend(options['fn'](thing))
                result.append('</li>')
            result.append('</ul>')
            return result
        source = u"{{#list people}}{{firstName}} {{lastName}}{{/list}}" 
        template = compiler.compile(source)
        context = {
            'people': [
                {'firstName': "Yehuda", 'lastName': "Katz"},
                {'firstName': "Carl", 'lastName': "Lerche"},
                {'firstName': "Alan", 'lastName': "Johnson"}
           ]}
        rendered = template(context, helpers={u'list': _list})
        self.assertEqual(
            u"<ul><li>Yehuda Katz</li><li>Carl Lerche</li>"\
            "<li>Alan Johnson</li></ul>",
            unicode(rendered))

    def test_escapes(self):
        self.assertEqual(u"""\
            <div class="entry">
              <h1>All about &lt;p&gt; Tags</h1>
              <div class="body">
                <p>This is a post about &lt;p&gt; tags</p>
              </div>
            </div>""",
            render(u"""\
            <div class="entry">
              <h1>{{title}}</h1>
              <div class="body">
                {{{body}}}
              </div>
            </div>""", {
            'title': u"All about <p> Tags",
            'body': u"<p>This is a post about &lt;p&gt; tags</p>",
            }))

