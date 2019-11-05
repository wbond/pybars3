# changelog

## 0.9.7

- Add support for whitespace control, `{{var~}}` (Handlebars 1.1)
- Add "list.length" support

## 0.9.6

- Add `template` method which creates a renderer from precompiled code.

## 0.9.5

- Fix resolving unicode fields in Python 2

## 0.9.4

- Add support for raw blocks (issues: #24, #25, #36)

## 0.9.3

- Add support for dynamic partials
- Add travis integration (flake8 and coverage)

## 0.9.2

- Make dictionary calls take precedence over attributes and .get (issue #16)
- Add else support in inverted if blocks (issue #17)
- Improve error parsing and reporting (issue #23)
- Port over a few more tests from handlebars.js

## 0.9.1

- Changed `pybars.__version__` tuple to `pybars.__version_info__`,
  `pybars.__version__` is now a string
- Added `Compiler().precompile(source)` that will return Python source code
  to allow for caching of compiled templates and easier debugging
- Template code now checks to ensure it is being run with the same version of
  pybars that is was generated with

## 0.8.0

- The library now always throws `pybars.PybarsError` on errors
- Added support for nested subexpressions
- Block helpers by themselves on lines no longer introduce any whitespace
- Added `tests.py` test runner and `--debug` flag
- Moved tests out of `pybars` namespace

## 0.7.2

- Fixed a bug with nested scopes and parent paths (`../`)

## 0.7.1

- Expose `pybars.Scope()` so helpers can properly scope data so `../` will work

## 0.7.0

- Added subexpression support

## 0.6.0

- Changed `False` to print `false` and `True` to print `true`
- Added support for `null` and `undefined` literals

## 0.5.1

- Added support for segment literals (`[foo bar]`)
- Fixed a bug related to newlines in the middle of tags
- Added support for single-quoted string literals
- Added the `lookup` helper
- Added support for quoted partial names

## 0.5.0

- Added support for negative integers
- Added support for parent acccess to data elements (`@../`)
- Added support for keyword args being passed to partials
- Added explicit `@_parent` data access
- Added `@root` data support
- Added `@index`, `@key`, `@first` and `@last` data access
- Added support for object attributes within the `#each` helper
- Added Python 3 support
