//! `GenerateCode`, the native replacement of `pybars.Compiler._generate_code`.

use std::panic::catch_unwind;
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};

use pybars3_compiler::{Error, Fallback, Options, PybarsVersion, UnicodeVersion};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString};

use crate::recursion::Recursion;

/// Why a call ran pybars' own `_generate_code`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Reason {
    /// The port is disabled in this interpreter (see the Python package's
    /// `unavailable_reason()`): every call runs pybars.
    Unavailable,
    /// `pybars._compiler.debug` is set: pybars prints the tree.
    Debug,
    /// The source is not exactly a `str`: pybars raises `PybarsError`, or
    /// parses a `str` subclass through its own methods.
    NotStr,
    /// The source has a lone surrogate, which Rust strings cannot hold.
    Surrogates,
    /// An integer literal that `int()` rejects: pybars raises `ValueError`.
    IntConversion,
    /// Nesting too deep for the port, or for the stack headroom left below
    /// `sys.getrecursionlimit()`: pybars compiles it or raises
    /// `RecursionError`.
    NestingDepth,
    /// The port panicked: a bug in pybars3-rs, which pybars' result hides.
    Panic,
    /// The port returned an error or code that the binding does not
    /// expect: a bug in pybars3-rs, which pybars' result hides.
    Internal,
}

impl Reason {
    const ALL: [Reason; 8] = [
        Reason::Unavailable,
        Reason::Debug,
        Reason::NotStr,
        Reason::Surrogates,
        Reason::IntConversion,
        Reason::NestingDepth,
        Reason::Panic,
        Reason::Internal,
    ];

    /// The reason's key in `counters()`.
    const fn name(self) -> &'static str {
        match self {
            Reason::Unavailable => "unavailable",
            Reason::Debug => "debug",
            Reason::NotStr => "not_str",
            Reason::Surrogates => "surrogates",
            Reason::IntConversion => "int_conversion",
            Reason::NestingDepth => "nesting_depth",
            Reason::Panic => "panic",
            Reason::Internal => "internal",
        }
    }
}

impl From<Fallback> for Reason {
    fn from(fallback: Fallback) -> Self {
        match fallback {
            Fallback::IntConversion => Reason::IntConversion,
            Fallback::NestingDepth => Reason::NestingDepth,
            // `Fallback` is non-exhaustive: a new reason runs pybars too.
            _ => Reason::Internal,
        }
    }
}

/// The objects of the installed pybars, and of the Python package, that
/// the fast path and the fallback need.
struct Pybars {
    /// `pybars._compiler`, for its `debug` flag.
    compiler_module: Py<PyAny>,
    /// `pybars._compiler.FunctionContainer`.
    function_container: Py<PyAny>,
    /// `pybars.Compiler._generate_code`.
    original: Py<PyAny>,
    /// `pybars.PybarsError`.
    error_class: Py<PyAny>,
    /// Makes a copy of pybars' compile grammar with a code builder of its
    /// own.
    new_compile_grammar: Py<PyAny>,
    /// The `contextvars.ContextVar` from which `pybars_rs.Compiler._compiler`
    /// reads the grammar of the fallback running in this context.
    fallback_grammar: Py<PyAny>,
}

/// Idle compile grammars (each with its own code builder) beyond which the
/// pool does not keep the ones that concurrent or nested fallbacks made.
const MAX_IDLE_GRAMMARS: usize = 16;

/// What the fast path produced for one call.
enum Attempt {
    /// pybars' `FunctionContainer` for the code.
    Container(Py<PyAny>),
    /// pybars' `PybarsError`, to raise.
    Raise(PyErr),
    /// Run pybars instead.
    Fallback(Reason),
}

/// `Compiler._generate_code(self, source)`, as a callable that the Python
/// package binds as a method without adding a Python frame.
///
/// It runs the port with the GIL released and returns pybars' own
/// `FunctionContainer`, or raises `pybars.PybarsError` with pybars' message.
/// Where the port does not reproduce pybars (see `Reason`), it calls
/// pybars' original method from native code, so that it runs at the stack
/// depth it would have had without pybars3-rs and raises exactly what pybars
/// raises, `RecursionError` included.
#[pyclass(frozen, module = "pybars_rs._native")]
pub(crate) struct GenerateCode {
    pybars: Pybars,
    /// The pybars release and the Unicode database to reproduce, or `None`
    /// when the port is disabled.
    versions: Option<(PybarsVersion, UnicodeVersion)>,
    /// Compile grammars that no fallback is using. Each fallback takes one,
    /// so that fallbacks in several threads, or nested in one (a `str`
    /// subclass can compile a template while pybars parses it), never share
    /// a code builder. The mutex is never held while Python code runs.
    idle_grammars: Mutex<Vec<Py<PyAny>>>,
    sys: Py<PyAny>,
    recursion: Recursion,
    fast_path: AtomicU64,
    fallbacks: [AtomicU64; Reason::ALL.len()],
}

#[pymethods]
impl GenerateCode {
    /// Build from the installed pybars.
    ///
    /// * `original`: `pybars.Compiler._generate_code`, the fallback;
    /// * `function_container`: `pybars._compiler.FunctionContainer`;
    /// * `compiler_module`: `pybars._compiler`, for its `debug` flag;
    /// * `error_class`: `pybars.PybarsError`;
    /// * `new_compile_grammar`: makes a copy of pybars' compile grammar
    ///   with a code builder of its own;
    /// * `fallback_grammar`: the `ContextVar` that `pybars_rs.Compiler._compiler`
    ///   reads;
    /// * `pybars_version`: the release whose compiler the installed pybars
    ///   has, such as `"0.9.7"`;
    /// * `unicode_version`: `unicodedata.unidata_version`.
    ///
    /// When `pybars_version` or `unicode_version` is `None`, the port is
    /// disabled, and every call runs `original`.
    #[new]
    #[pyo3(signature = (*, original, function_container, compiler_module, error_class, new_compile_grammar, fallback_grammar, pybars_version, unicode_version))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        original: Py<PyAny>,
        function_container: Py<PyAny>,
        compiler_module: Py<PyAny>,
        error_class: Py<PyAny>,
        new_compile_grammar: Py<PyAny>,
        fallback_grammar: Py<PyAny>,
        pybars_version: Option<&str>,
        unicode_version: Option<&str>,
    ) -> PyResult<Self> {
        let versions = match (pybars_version, unicode_version) {
            (Some(pybars), Some(unicode)) => Some(crate::parse_versions(pybars, unicode)?),
            _ => None,
        };
        Ok(GenerateCode {
            pybars: Pybars {
                compiler_module,
                function_container,
                original,
                error_class,
                new_compile_grammar,
                fallback_grammar,
            },
            versions,
            idle_grammars: Mutex::new(Vec::new()),
            sys: py.import("sys")?.into_any().unbind(),
            recursion: Recursion::of(py),
            fast_path: AtomicU64::new(0),
            fallbacks: Default::default(),
        })
    }

    /// `compiler._generate_code(source)`.
    fn __call__(
        &self,
        py: Python<'_>,
        compiler: &Bound<'_, PyAny>,
        source: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        match self.attempt(py, source)? {
            Attempt::Container(container) => {
                self.fast_path.fetch_add(1, Ordering::Relaxed);
                Ok(container)
            }
            Attempt::Raise(error) => {
                self.fast_path.fetch_add(1, Ordering::Relaxed);
                Err(error)
            }
            Attempt::Fallback(reason) => {
                self.fallbacks[reason as usize].fetch_add(1, Ordering::Relaxed);
                self.fall_back(py, compiler, source)
            }
        }
    }

    /// How many calls the port answered (`fast_path`) and how many ran
    /// pybars, by reason.
    fn counters<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let counters = PyDict::new(py);
        counters.set_item("fast_path", self.fast_path.load(Ordering::Relaxed))?;
        for reason in Reason::ALL {
            counters.set_item(
                reason.name(),
                self.fallbacks[reason as usize].load(Ordering::Relaxed),
            )?;
        }
        Ok(counters)
    }

    /// The fast path alone, for tests and diagnostics: pybars'
    /// `FunctionContainer`, or the name of the reason pybars would run
    /// instead. Raises `PybarsError` as `__call__` does.
    fn try_fast_path(&self, py: Python<'_>, source: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        match self.attempt(py, source)? {
            Attempt::Container(container) => Ok(container),
            Attempt::Raise(error) => Err(error),
            Attempt::Fallback(reason) => Ok(PyString::new(py, reason.name()).into_any().unbind()),
        }
    }

    /// The deepest nesting that the fast path compiles when called from the
    /// current stack depth.
    fn nesting_limit(&self, py: Python<'_>) -> PyResult<usize> {
        self.recursion.headroom(py, self.sys.bind(py))
    }
}

impl GenerateCode {
    fn attempt(&self, py: Python<'_>, source: &Bound<'_, PyAny>) -> PyResult<Attempt> {
        let Some((pybars_version, unicode_version)) = self.versions else {
            return Ok(Attempt::Fallback(Reason::Unavailable));
        };
        let Ok(source) = source.cast_exact::<PyString>() else {
            return Ok(Attempt::Fallback(Reason::NotStr));
        };
        if self
            .pybars
            .compiler_module
            .bind(py)
            .getattr("debug")?
            .is_truthy()?
        {
            return Ok(Attempt::Fallback(Reason::Debug));
        }
        let Ok(text) = source.to_str() else {
            return Ok(Attempt::Fallback(Reason::Surrogates));
        };
        let options = Options::new(pybars_version, unicode_version)
            .with_int_max_str_digits(self.int_max_str_digits(py)?)
            .with_nesting_limit(self.recursion.headroom(py, self.sys.bind(py))?);
        // Copy the text out of the `str` before detaching from the
        // interpreter: the copy is cheap next to the compile.
        let text = text.to_owned();
        let Ok(result) =
            py.detach(move || catch_unwind(|| pybars3_compiler::precompile(&text, &options)))
        else {
            return Ok(Attempt::Fallback(Reason::Panic));
        };
        Ok(match result {
            // pybars' `FunctionContainer` adds the header of the pybars that
            // is installed, which is this release's.
            Ok(code) => match code.strip_prefix(pybars_version.header()) {
                Some(body) => {
                    Attempt::Container(self.pybars.function_container.call1(py, ("render", body))?)
                }
                None => Attempt::Fallback(Reason::Internal),
            },
            Err(Error::Template(error)) => Attempt::Raise(PyErr::from_value(
                self.pybars.error_class.bind(py).call1((error.message(),))?,
            )),
            Err(Error::Fallback(fallback)) => Attempt::Fallback(fallback.into()),
            // `Error` is non-exhaustive: a new kind of error runs pybars too.
            Err(_) => Attempt::Fallback(Reason::Internal),
        })
    }

    /// pybars' own `_generate_code`, with a compile grammar (and so a code
    /// builder) that no other call is using.
    ///
    /// The grammar is taken and set before the call and put back after it,
    /// with no Python frame around the call itself, so that pybars runs at
    /// the stack depth it would have had without pybars3-rs.
    fn fall_back(
        &self,
        py: Python<'_>,
        compiler: &Bound<'_, PyAny>,
        source: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        let grammar = match self.take_idle_grammar() {
            Some(grammar) => grammar,
            None => self.pybars.new_compile_grammar.call0(py)?,
        };
        let fallback_grammar = self.pybars.fallback_grammar.bind(py);
        let token = fallback_grammar.call_method1("set", (&grammar,))?;
        let result = self
            .recursion
            .with_pybars_budget(py, || self.pybars.original.call1(py, (compiler, source)));
        let reset = fallback_grammar.call_method1("reset", (token,));
        self.put_idle_grammar(grammar);
        reset?;
        result
    }

    fn take_idle_grammar(&self) -> Option<Py<PyAny>> {
        self.idle_grammars
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .pop()
    }

    fn put_idle_grammar(&self, grammar: Py<PyAny>) {
        let mut idle = self
            .idle_grammars
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if idle.len() < MAX_IDLE_GRAMMARS {
            idle.push(grammar);
        }
    }

    /// `sys.get_int_max_str_digits()`, which a program can change at any
    /// time (0 when the interpreter has no limit).
    fn int_max_str_digits(&self, py: Python<'_>) -> PyResult<usize> {
        let sys = self.sys.bind(py);
        if !sys.hasattr("get_int_max_str_digits")? {
            return Ok(0);
        }
        sys.call_method0("get_int_max_str_digits")?.extract()
    }
}
