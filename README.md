#pybars - handlebars.js for python

Pybars provides a template system for Python which is compatible with
handlebars.js.

##Installation

This Python 3 fork of pybars requires [pymeta](https://launchpad.com/pymeta)
and [testtools](https://github.com/testing-cabal/testtools) that also run on
Python 3. Currently this requires installing custom forks.

```bash
pip install git+https://github.com/wbond/testtools
pip install git+https://github.com/wbond/pymeta

pip install git+https://github.com/wbond/pybars
```

## Usage

For details on the template language see the http://handlebarsjs.com
documentation.

Typical usage:

```python
# Get a compiler
from pybars import Compiler
compiler = Compiler()

# Compile the template
source = u"{{>header}}{{#list people}}{{firstName}} {{lastName}}{{/list}}"
template = compiler.compile(source)

# Add any special helpers
def _list(this, options, items):
    result = [u'<ul>']
    for thing in items:
        result.append(u'<li>')
        result.extend(options['fn'](thing))
        result.append(u'</li>')
    result.append(u'</ul>')
    return result
helpers = {'list': _list}

# Add partials
header = compiler.compile('<h1>People</h1>')
partials = {'header': header}

# Render the template
output = template({
    'people': [
        {'firstName': "Yehuda", 'lastName': "Katz"},
        {'firstName': "Carl", 'lastName': "Lerche"},
        {'firstName': "Alan", 'lastName': "Johnson"}
    ]}, helpers=helpers, partials=partials)

print(output)
```

The generated output will be:

```html
<h1>People</h1><ul><li>Yehuda Katz</li><li>Carl Lerche</li><li>Alan Johnson</li></ul>
```

### Handlers

Translating the engine to python required slightly different calling
conventions to the JS version:

* block helpers should accept `this, options, *args, **kwargs`
* other helpers should accept `this, *args, **kwargs`
* closures in the context should accept `this, *args, **kwargs`

A template like `{{foo bar quux=1}}` will pass `bar` as a positional argument and
`quux` as a keyword argument. Keyword arguments have to be non-reserved words in
Python. For instance, `print` as a keyword argument will fail.

## Implementation Notes

Templates with literal boolean arguments like `{{foo true}}` will have the
argument mapped to Python's `True` or `False` as appropriate.

For efficiency, rather that passing strings round, pybars passes a subclass of
list (`strlist`) which has a `__unicode__` implementation that returns
`u"".join(self)`. Template helpers can return any of `list`, `tuple`, `unicode` or
`strlist` instances. `strlist` exists to avoid quadratic overheads in string
processing during template rendering. Helpers that are in inner loops *should*
return `list` or `strlist` for the same reason.

**NOTE** The `strlist` takes the position of SafeString in the js implementation:
when returning a strlist it will not be escaped, even in a regular `{{}}`
expansion.

```python
import pybars

source = u"{{bold name}}"

compiler = pybars.Compiler()
template = compiler.compile(source)

def _bold(this, name):
    return pybars.strlist(['<strong>', name, '</strong>'])
helpers = {'bold': _bold}

output = template({'name': 'Will'}, helpers=helpers)
print(output)
```

The `data` facility from the JS implementation has not been ported at this
point, if there is demand for it it would be quite easy to add. Similarly
the `stringParams` feature has not been ported - quote anything you wish to force
to a string in a helper call.

## Dependencies

* Python 2.6-2.7, 3.3+
* PyMeta (Python 3 fork, https://github.com/wbond/pymeta)

## Testing Dependencies

* testtools (Python 3 fork, https://github.com/wbond/testtools)
* subunit (http://pypi.python.org/pypi/python-subunit) (optional)

## Development

Upstream development takes place at https://launchpad.net/pybars.

To run the tests use the runner of your choice, the test suite is
pybars.tests.test_suite.

For instance::

```bash
python -m testtools.run pybars.tests.test_suite
```

pybars is testrepository enabled, so you can just do:

```bash
testr init
testr run
```

## Copyright

```
Copyright (c) 2012, Canonical Ltd

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, version 3 only.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
GNU Lesser General Public License version 3 (see the file LICENSE).
```