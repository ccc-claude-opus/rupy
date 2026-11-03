//! Python's standard library for rupy, in Rust: each module mirrors the CPython
//! module of the same name (the same results, checked against CPython by the
//! programs in `tests/corpus/py/std_*.py`), and is declared to rupy by a stub
//! `src/lib/NAME.pyi`, so a rupy program simply writes `import shlex`.

pub mod fnmatch;
#[cfg(feature = "gymnasium")]
pub mod gymnasium;
pub mod html;
mod html_tables;
#[cfg(feature = "numpy")]
pub mod numpy;
pub mod os;
#[cfg(feature = "http")]
pub mod rupy_http;
pub mod rupy_json;
#[cfg(feature = "plot")]
pub mod ruai_plot;
pub mod shlex;
#[cfg(feature = "sklearn")]
pub mod sklearn;
pub mod subprocess;
pub mod sys;
pub mod time;
#[cfg(feature = "torch")]
pub mod torch;
