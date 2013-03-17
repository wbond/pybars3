# Copyright (c) 2008-2010
# Allen Short
# Waldemar Kornewald
#
# Soli Deo Gloria.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""A single helper from pymeta which was too good to pass up but not usable as-was.

See https://bugs.launchpad.net/bugs/928486
"""

from itertools import count
import linecache
import sys
import os
import tokenize
from types import ModuleType as module

if sys.version_info >= (3,):
    def updatecache(filename, module_globals=None):
        """Update a cache entry and return its list of lines.
        If something's wrong, print a message, discard the cache entry,
        and return an empty list."""

        if filename in linecache.cache:
            del linecache.cache[filename]
        if not filename or (filename.startswith('<') and filename.endswith('>')):
            return []

        fullname = filename
        try:
            stat = os.stat(fullname)
        except OSError:
            basename = filename

            # Try for a __loader__, if available
            if module_globals and '__loader__' in module_globals:
                name = module_globals.get('__name__')
                loader = module_globals['__loader__']
                get_source = getattr(loader, 'get_source', None)

                if name and get_source:
                    try:
                        data = get_source(name)
                    except (ImportError, IOError):
                        pass
                    else:
                        if data is None:
                            # No luck, the PEP302 loader cannot find the source
                            # for this module.
                            return []
                        linecache.cache[filename] = (
                            len(data), None,
                            ["%s\n" % line for line in data.splitlines()], fullname
                        )
                        return linecache.cache[filename][2]

            # Try looking through the module search path, which is only useful
            # when handling a relative filename.
            if os.path.isabs(filename):
                return []

            for dirname in sys.path:
                try:
                    fullname = os.path.join(dirname, basename)
                except (TypeError, AttributeError):
                    # Not sufficiently string-like to do anything useful with.
                    continue
                try:
                    stat = os.stat(fullname)
                    break
                except os.error:
                    pass
            else:
                return []
        try:
            with tokenize.open(fullname) as fp:
                lines = fp.readlines()
        except IOError:
            return []
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        size, mtime = stat.st_size, stat.st_mtime
        linecache.cache[filename] = size, mtime, lines, fullname
        return lines

    linecache.updatecache = updatecache


class GeneratedCodeLoader(object):
    """
    Object for use as a module's __loader__, to display generated
    source.
    """
    def __init__(self, source):
        self.source = source.encode('utf8')
    def get_source(self, name):
        return self.source

next_filename = iter(count())

def moduleFromSource(source, className, superclass=None, globalsDict=None,
    registerModule=True):
    modname = "pymeta_grammar__" + className + "__" + str(next(next_filename))
    filename = "/pymeta_generated_code/" + modname + ".py"
    mod = module(modname)
    if globalsDict:
        mod.__dict__.update(globalsDict)
    mod.__name__ = modname
    if superclass:
        mod.__dict__[superclass.__name__] = superclass
        mod.__dict__["GrammarBase"] = superclass
    mod.__loader__ = GeneratedCodeLoader(source)
    code = compile(source, filename, "exec")
    eval(code, mod.__dict__)
    fullGlobals = dict(getattr(mod.__dict__[className], "globals", None) or {})
    fullGlobals.update(globalsDict)
    mod.__dict__[className].globals = fullGlobals
    if registerModule:
        sys.modules[modname] = mod
    linecache.getlines(filename, mod.__dict__)
    return mod.__dict__[className]
