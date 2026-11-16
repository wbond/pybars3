"""The tests of pybars3-rs, which compare it with the installed pybars.

The tests are about the Rust compiler, so they refuse to run when pybars_rs
falls back to pybars for every template (``pybars_rs.unavailable_reason()``
says why), unless ``PYBARS_RS_DISABLE`` asks for that.

Environment variables make the runs longer: ``HYPOTHESIS_PROFILE`` (``ci``,
the default, ``dev`` or ``long``), ``EXHAUSTIVE_MAX_LENGTH`` and
``FUZZ_ITERATIONS``.
"""

import os
import warnings

from hypothesis import HealthCheck, settings

# pybars3 0.9.6 has '\s' and '\w' in plain string literals.
warnings.simplefilter('ignore', SyntaxWarning)
warnings.filterwarnings('ignore', 'invalid escape sequence', DeprecationWarning)

import pybars_rs  # noqa: E402

settings.register_profile('ci', max_examples=300, deadline=None, derandomize=True)
settings.register_profile('long', max_examples=20000, deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.register_profile('dev', max_examples=100, deadline=None)
settings.load_profile(os.environ.get('HYPOTHESIS_PROFILE', 'ci'))

if not pybars_rs.is_available() and os.environ.get('PYBARS_RS_DISABLE', '') in ('', '0'):
    raise RuntimeError(
        "pybars_rs' Rust compiler is unavailable: %s. If pybars/_compiler.py changed, see the Development "
        'section of pybars3-rs/readme.md.' % pybars_rs.unavailable_reason()
    )
