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

"""A template system for Python which is compatible with handlebars.js.

For details on the template language see the http://handlebarsjs.com/
documentation.

Translating the engine to python required slightly different calling
conventions to the JS version:

* block helpers take (this, options, *args, **kwargs)

* other helpers take (this, *args, **kwargs)

* closures in the context take (this, *args, **kwargs)

A template like '{{foo bar quux=1}}' will pass bar as a positional argument and
quux as a keyword argument. Keyword arguments have to be non-reserved words in
Python. For instance, 'print' as a keyword argument will fail.

Templates with literal boolean arguments like '{{foo true}}' will have the
argument mapped to Python's True or False as appropriate.

For efficiency, rather that passing strings round, pybars passes a subclass of
list ('liststr') which has a __unicode__ implementation that returns
u"".join(self). Template helpers can return any of list, tuple, unicode or
liststr instances. liststr exists to avoid quadratic overheads in string
processing during template rendering. Helpers that are in inner loops *should*
return list or liststr for the same reason.

**NOTE** The liststr takes the position of SafeString in the js implementation:
when returning a liststr it will not be escaped, even in a regular {{}}
expansion.

The 'data' facility from the JS implementation has not been ported at this
point, if there is demand for it it would be quite easy to add. Similarly
the stringParams feature has not been ported - quote anything you wish to force
to a string in a helper call.

Typical usage:

* Grab a compiler:

  >>> from pybars import Compiler
  >>> compiler = Compiler()

* Register any extensions you need:

  >>> def _list(this, options, items):
  ...     result = [u'<ul>']
  ...     for thing in items:
  ...         result.append(u'<li>')
  ...         result.extend(options['fn'](thing))
  ...         result.append(u'</li>')
  ...     result.append(u'</ul>')
  ...     return result
  >>> compiler.register_helper(u'list', _list)

* And compile your template:

  >>> source = u"{{#list people}}{{firstName}} {{lastName}}{{/list}}"
  >>> template = compiler.compile(source)

* You can now render it:

  >>> template({
  ...     'people': [
  ...         {'firstName': "Yehuda", 'lastName': "Katz"},
  ...         {'firstName': "Carl", 'lastName': "Lerche"},
  ...         {'firstName': "Alan", 'lastName': "Johnson"}
  ...    ]})
  <ul><li>Yehuda Katz</li><li>Carl Lerche</li><li>Alan Johnson</li></ul>
"""

# same format as sys.version_info: "A tuple containing the five components of
# the version number: major, minor, micro, releaselevel, and serial. All
# values except releaselevel are integers; the release level is 'alpha',
# 'beta', 'candidate', or 'final'. The version_info value corresponding to the
# Python version 2.0 is (2, 0, 0, 'final', 0)."  Additionally we use a
# releaselevel of 'dev' for unreleased under-development code.
#
# If the releaselevel is 'alpha' then the major/minor/micro components are not
# established at this point, and setup.py will use a version of next-$(revno).
# If the releaselevel is 'final', then the tarball will be major.minor.micro.
# Otherwise it is major.minor.micro~$(revno).
__version__ = (0, 0, 1, 'beta', 0)

__all__ = [
    'Compiler',
    'helpers',
    'log',
    'strlist',
    ]

from pybars._compiler import (
    Compiler,
    global_helpers as helpers,
    strlist,
    )


log = lambda value:None
