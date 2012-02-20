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
import linecache, sys
from types import ModuleType as module

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
