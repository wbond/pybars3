//! `pybars_rs._native`, the extension module of the pybars3-rs Python
//! package.
//!
//! * `generate_code`: `GenerateCode` replaces `pybars.Compiler._generate_code`,
//!   the method that `compile()`, `precompile()` and `template()` use to
//!   turn template text into Python source, and falls back to pybars' own
//!   method where the port does not reproduce pybars.
//! * `recursion`: the stack headroom for pybars, and the only `unsafe` code
//!   (calls to CPython's recursion counter on CPython 3.10 and 3.11).
//! * `precompile` here: the port alone, for tests and diagnostics.

#![deny(unsafe_code)]

mod generate_code;
mod recursion;

use std::panic::catch_unwind;

use pybars3_compiler::{Error, Options, PybarsVersion, UnicodeVersion};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use crate::generate_code::GenerateCode;

/// Parse `pybars.__version__` and `unicodedata.unidata_version`.
fn parse_versions(pybars: &str, unicode: &str) -> PyResult<(PybarsVersion, UnicodeVersion)> {
    let pybars = pybars
        .parse()
        .map_err(|error: pybars3_compiler::UnknownPybarsVersion| {
            PyValueError::new_err(error.to_string())
        })?;
    let unicode = unicode
        .parse()
        .map_err(|error: pybars3_compiler::UnknownUnicodeVersion| {
            PyValueError::new_err(error.to_string())
        })?;
    Ok((pybars, unicode))
}

/// The port alone, for tests: `("code", code)`, `("error", message,
/// position)` or `("fallback", reason)`.
#[pyfunction]
#[pyo3(signature = (source, /, *, pybars_version, unicode_version, int_max_str_digits = Options::DEFAULT_INT_MAX_STR_DIGITS, nesting_limit = Options::MAX_NESTING_LIMIT))]
fn precompile<'py>(
    py: Python<'py>,
    source: &str,
    pybars_version: &str,
    unicode_version: &str,
    int_max_str_digits: usize,
    nesting_limit: usize,
) -> PyResult<Bound<'py, PyTuple>> {
    let (pybars_version, unicode_version) = parse_versions(pybars_version, unicode_version)?;
    let options = Options::new(pybars_version, unicode_version)
        .with_int_max_str_digits(int_max_str_digits)
        .with_nesting_limit(nesting_limit);
    let source = source.to_owned();
    let Ok(result) =
        py.detach(move || catch_unwind(|| pybars3_compiler::precompile(&source, &options)))
    else {
        return ("fallback", "panic").into_pyobject(py);
    };
    match result {
        Ok(code) => ("code", code).into_pyobject(py),
        Err(Error::Template(error)) => {
            ("error", error.message(), error.position()).into_pyobject(py)
        }
        Err(Error::Fallback(fallback)) => ("fallback", fallback.name()).into_pyobject(py),
        Err(_) => ("fallback", "internal").into_pyobject(py),
    }
}

#[pymodule(name = "_native", gil_used = false)]
fn native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    module.add_class::<GenerateCode>()?;
    module.add_function(wrap_pyfunction!(precompile, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add(
        "PYBARS_VERSIONS",
        PyTuple::new(py, PybarsVersion::ALL.map(PybarsVersion::as_str))?,
    )?;
    let headers = PyDict::new(py);
    for version in PybarsVersion::ALL {
        headers.set_item(version.as_str(), version.header())?;
    }
    module.add("HEADERS", headers)?;
    module.add("MAX_NESTING_LIMIT", Options::MAX_NESTING_LIMIT)?;
    module.add(
        "UNICODE_VERSIONS",
        PyTuple::new(py, UnicodeVersion::ALL.map(UnicodeVersion::as_str))?,
    )?;
    Ok(())
}
