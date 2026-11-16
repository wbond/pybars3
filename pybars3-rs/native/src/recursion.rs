//! The recursion budget that pybars would have had: how deep a template
//! the port may compile from the current stack, and how to call pybars'
//! own method without changing its budget.
//!
//! This is the only module that calls CPython directly
//! (`Py_EnterRecursiveCall` and `Py_LeaveRecursiveCall`, which PyO3 has no
//! safe API for), and only on CPython 3.10 and 3.11, where Python frames and
//! calls into native code share one recursion counter. Without them,
//! `RecursionError` would come one frame early there.

#![allow(unsafe_code)]

use pybars3_compiler::Options;
use pyo3::exceptions::PyValueError;
use pyo3::ffi;
use pyo3::prelude::*;

/// Python frames that pybars needs, above the frame that calls
/// `_generate_code`, to compile a template of nesting depth `depth` (see
/// `Options::with_nesting_limit`): at most
/// `BASE_FRAMES + FRAMES_PER_LEVEL * depth`.
///
/// `tools/calibrate_recursion.py` measures pybars on CPython 3.10 to 3.15:
/// it needs at most `24 + 18 * depth` to `26 + 18 * depth` frames (an
/// `{{else}}` branch nested in each block is the steepest shape). These
/// constants leave a margin, and `tests/test_recursion.py` checks that
/// pybars3-rs and pybars agree at every recursion limit around each template's
/// boundary.
const BASE_FRAMES: usize = 40;
/// See [`BASE_FRAMES`].
const FRAMES_PER_LEVEL: usize = 20;

/// How the interpreter counts recursion.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Recursion {
    /// CPython 3.12 and later: `sys.getrecursionlimit()` bounds Python
    /// frames only, and calls into native code have a separate counter.
    Frames,
    /// CPython 3.10 and 3.11: Python frames and calls into native code
    /// share one counter. The call into the native `_generate_code` took
    /// one unit that pybars' own `self._generate_code(source)` does not
    /// take.
    SharedWithNativeCalls,
}

impl Recursion {
    pub(crate) fn of(py: Python<'_>) -> Self {
        if py.version_info() >= (3, 12) {
            Recursion::Frames
        } else {
            Recursion::SharedWithNativeCalls
        }
    }

    /// The deepest nesting for which pybars, called from the current stack
    /// depth, stays below `sys.getrecursionlimit()`.
    pub(crate) fn headroom(self, py: Python<'_>, sys: &Bound<'_, PyAny>) -> PyResult<usize> {
        let deepest = BASE_FRAMES + FRAMES_PER_LEVEL * Options::MAX_NESTING_LIMIT;
        if self == Recursion::SharedWithNativeCalls {
            // Count in the units of the shared counter, of which this call
            // holds one that the fallback gives back to pybars.
            return Ok(nesting_for(units_left(py, deepest) + 1));
        }
        let limit: usize = sys.call_method0("getrecursionlimit")?.extract()?;
        // Usually the stack is shallow enough for the deepest template the
        // port compiles: `sys._getframe(n)` raises ValueError when there are
        // `n` or fewer frames, which takes one call to find out.
        if let Some(budget) = limit.checked_sub(deepest) {
            match sys.call_method1("_getframe", (budget,)) {
                Err(error) if error.is_instance_of::<PyValueError>(py) => {
                    return Ok(Options::MAX_NESTING_LIMIT);
                }
                Err(error) => return Err(error),
                Ok(_) => {}
            }
        }
        let depth = stack_depth(sys)?;
        Ok(nesting_for(limit.saturating_sub(depth)))
    }

    /// Run `call`, a call to pybars' own `_generate_code`, with the
    /// recursion budget it would have had if Python had called it directly.
    pub(crate) fn with_pybars_budget<T>(
        self,
        py: Python<'_>,
        call: impl FnOnce() -> PyResult<T>,
    ) -> PyResult<T> {
        if self == Recursion::Frames {
            return call();
        }
        // SAFETY: the GIL is held (`py`), and CPython entered a recursive
        // call when it called the native `_generate_code`, which leaves it
        // after returning. This gives that unit back while pybars runs; it
        // is taken again below.
        unsafe { ffi::Py_LeaveRecursiveCall() };
        let result = call();
        // SAFETY: the GIL is held and the argument is a C string literal.
        // The depth is back to the one at which CPython entered this call,
        // so entering again succeeds.
        let failed =
            unsafe { ffi::Py_EnterRecursiveCall(c" while calling a Python object".as_ptr()) } != 0;
        if failed {
            return Err(PyErr::fetch(py));
        }
        result
    }
}

/// The units of the shared counter left before `RecursionError`, up to
/// `wanted`, found by entering recursive calls and leaving them again.
fn units_left(py: Python<'_>, wanted: usize) -> usize {
    let mut entered = 0;
    while entered < wanted {
        // SAFETY: the GIL is held (`py`) and the argument is a C string
        // literal. A failed `Py_EnterRecursiveCall` leaves the counter as it
        // was and sets a RecursionError, which is cleared here.
        if unsafe { ffi::Py_EnterRecursiveCall(c"".as_ptr()) } != 0 {
            drop(PyErr::take(py));
            break;
        }
        entered += 1;
    }
    for _ in 0..entered {
        // SAFETY: the GIL is held, and this leaves a call entered above.
        unsafe { ffi::Py_LeaveRecursiveCall() };
    }
    entered
}

/// The deepest nesting that pybars compiles with `frames` frames to spare.
fn nesting_for(frames: usize) -> usize {
    (frames.saturating_sub(BASE_FRAMES) / FRAMES_PER_LEVEL).min(Options::MAX_NESTING_LIMIT)
}

/// The number of Python frames on the stack.
fn stack_depth(sys: &Bound<'_, PyAny>) -> PyResult<usize> {
    let mut depth = 0;
    let mut frame = sys.call_method1("_getframe", (0,))?;
    while !frame.is_none() {
        depth += 1;
        frame = frame.getattr("f_back")?;
    }
    Ok(depth)
}
