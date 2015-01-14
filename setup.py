#!/usr/bin/env python
#
# Copyright (c) 2012-2015, Canonical Ltd, Will Bond, Mjumbe Wawatu Ukweli
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


from distutils.core import setup
import os.path

description = open(
        os.path.join(os.path.dirname(__file__), 'README.md'), 'r').read()

setup(name='pybars3',
      version='0.5.0',
      description='Handlebars.js templating for Python 3 and 2',
      long_description=description,
      author='wbond, mjumbewu',
      author_email='will@wbond.net, mjumbewu@gmail.com',
      url='https://github.com/wbond/pybars3',
      packages=['pybars', 'pybars.tests'],
      package_dir = {'':'.'},
      classifiers = [
          'Development Status :: 3 - Beta',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: 3.4'
          ],
      install_requires = [
          'PyMeta3',
          ],
      extras_require = dict(
          test=[
              'fixtures',
              'testtools',
              ]
          ),
      )
