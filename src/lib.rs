//! rupy: a typed subset of Python compiled to readable Rust, or straight to
//! WebAssembly. (It was py0, the `ruai py` command of [ruai](https://crates.io/crates/ruai).)
//!
//! * The translator (feature `translator`, on by default): `front` parses (ruff)
//!   and type-checks into the IR, `own` infers ownership and rejects programs
//!   whose meaning depends on shared mutable objects, `gen` prints Rust that
//!   uses the [`pyrt`] runtime, and [`wasm`] compiles the IR to a WasmGC module.
//! * [`pyrt`], the runtime of translated programs (always built; they depend on
//!   `rupy` with `default-features = false`). Its packages are features: `re`,
//!   `http` (`rupy.http`), `numpy`, `sklearn`, and, on ruai's engine,
//!   `gymnasium`, `torch` and `plot` (`ruai.plot`); `python` calls real Python
//!   libraries through an embedded CPython.
//! * The `rupy` command (`rupy run prog.py`, `emit`, `check`, `wasm`, `test`, ...),
//!   and `ruai-py` / `ruai-agent`, which keep `ruai py` and `ruai agent` working.

// Style lints of newer clippy versions in the code merged from py2rs; behavior
// is pinned by the CPython differential tests (tests/corpus), not restyled here.
#![allow(clippy::cloned_ref_to_slice_refs, clippy::collapsible_if, clippy::excessive_precision, clippy::if_same_then_else, clippy::large_enum_variant, clippy::let_and_return, clippy::manual_is_multiple_of, clippy::manual_repeat_n, clippy::match_like_matches_macro, clippy::match_single_binding, clippy::needless_lifetimes, clippy::only_used_in_recursion, clippy::redundant_closure, clippy::redundant_locals, clippy::replace_box, clippy::type_complexity, clippy::unnecessary_sort_by, clippy::unnecessary_unwrap)]

pub mod pyrt;
pub mod rng;

#[cfg(feature = "translator")]
pub mod diag;
#[cfg(feature = "translator")]
pub mod exc;
#[cfg(feature = "translator")]
pub mod front;
#[cfg(feature = "translator")]
pub mod fuzz;
#[cfg(feature = "translator")]
pub mod gen;
#[cfg(feature = "translator")]
pub mod ir;
#[cfg(feature = "translator")]
pub mod modules;
#[cfg(feature = "translator")]
pub mod own;
#[cfg(feature = "translator")]
pub mod project;
#[cfg(feature = "translator")]
pub mod pyo3;
#[cfg(feature = "translator")]
pub mod wasm;
#[cfg(feature = "translator")]
pub mod stubgen;

#[cfg(feature = "translator")]
pub use diag::Error;

#[cfg(feature = "translator")]
/// What py2rs decided about ownership, per function (`py2rs explain`).
pub fn explain(src: &str) -> Result<String, Error> {
    use ir::Ty;
    let prog = front::lower(src)?;
    let own = own::analyze(&prog)?;
    let exc = exc::analyze(&prog)?;
    gen::generate(&prog, &own, &exc)?;
    let clones = gen::clones();
    let mut out = String::new();
    for (fid, f) in prog.funcs.iter().enumerate() {
        if !f.dispatch.is_empty() {
            continue;
        }
        let name = match f.class {
            Some(c) => format!("{}.{}", prog.classes[c].name, f.name),
            None if fid == prog.main => "<module>".to_string(),
            None => f.name.clone(),
        };
        out += &format!("{} (line {})\n", name, f.line);
        if f.self_var.is_some() && !f.is_init {
            out += &format!("  self: {}\n", if own.self_mut[fid] { "&mut self (modifies the object)" } else { "&self (only reads)" });
        }
        for (i, q) in f.params.iter().enumerate() {
            let v = &f.vars[q.var];
            let t = gen::rty(&v.ty, &prog);
            let rt = match &v.ty {
                Ty::Str => "&str".to_string(),
                Ty::List(e) => format!("&[{}]", gen::rty(e, &prog)),
                _ => format!("&{}", t),
            };
            let how = match own.params[fid][i] {
                own::Mode::Copy => format!("{} (copied: a number / bool / tuple of them)", t),
                own::Mode::Ref => format!("{} (only read)", rt),
                own::Mode::Mut => format!("&mut {} (modified in place)", t),
                own::Mode::Owned if own.owned_local[fid][i] => format!("{} (rebound inside: callers may pass a copy)", t),
                own::Mode::Owned => format!("{} (kept or returned: callers move it, or it is copied)", t),
            };
            let forced = if q.force.is_some() { " [annotated]" } else { "" };
            out += &format!("  param {}: {}{}\n", v.name, how, forced);
        }
        if exc.fallible[fid] {
            let mut ks: Vec<&String> = exc.may[fid].iter().collect();
            ks.sort();
            out += &format!("  returns Result<_, PyErr>: a caller catches {}\n", ks.iter().map(|k| k.as_str()).collect::<Vec<_>>().join(", "));
        }
        let mut names = |set: &std::collections::HashSet<usize>, what: &str| {
            let mut v: Vec<&str> = set.iter().map(|x| f.vars[*x].name.as_str()).collect();
            v.sort();
            if !v.is_empty() {
                out += &format!("  {}: {}\n", what, v.join(", "));
            }
        };
        names(&own.views[fid], "references (&T, only read other objects)");
        names(&own.mut_views[fid], "mutable references (&mut T into a container)");
        names(&own.consumed[fid], "narrowed values that take the Optional's value");
        let mut cs: Vec<&(usize, u32, String)> = clones.iter().filter(|c| c.0 == fid).collect();
        cs.sort_by_key(|c| c.1);
        cs.dedup();
        for (_, line, what) in cs {
            out += &format!("  line {}: copies `{}` (the original is still used, or Python would share it)\n", line, what);
        }
    }
    Ok(out)
}

#[cfg(feature = "translator")]
/// Translate Python source to the Rust source of a program.
pub fn translate(src: &str) -> Result<String, Error> {
    let prog = front::lower(src)?;
    let own = own::analyze(&prog)?;
    let exc = exc::analyze(&prog)?;
    gen::generate(&prog, &own, &exc)
}

#[cfg(feature = "translator")]
/// Compile a program file (and the local modules it imports) to WebAssembly,
/// without Rust (see [`wasm`]).
pub fn wasm_file(path: &std::path::Path) -> Result<Vec<u8>, String> {
    front::set_program_dir(path.parent().map(|p| p.to_path_buf()));
    let c = modules::combine(path).map_err(|(f, _, e)| format!("{}:{}: {}", f.display(), e.line, e.msg))?;
    let prog = front::lower_modules(&c.src, &front::default_stub_dirs(), &c.modules).map_err(|e| {
        let (f, _, line) = c.locate(e.line);
        format!("{}:{}: {}", f.display(), line, e.msg)
    })?;
    own::analyze(&prog).map_err(|e| {
        let (f, _, line) = c.locate(e.line);
        format!("{}:{}: {}", f.display(), line, e.msg)
    })?;
    wasm::compile(&prog).map_err(|e| format!("{}: {}", path.display(), e))
}

#[cfg(feature = "translator")]
/// Translate a program file (and the local modules it imports).
pub fn translate_file(path: &std::path::Path) -> Result<String, modules::FileError> {
    front::set_program_dir(path.parent().map(|p| p.to_path_buf()));
    let c = modules::combine(path)?;
    let r = (|| {
        let prog = front::lower_modules(&c.src, &front::default_stub_dirs(), &c.modules)?;
        let own = own::analyze(&prog)?;
        let exc = exc::analyze(&prog)?;
        gen::generate(&prog, &own, &exc)
    })();
    r.map_err(|mut e| {
        let (f, src, line) = c.locate(e.line);
        e.line = line;
        (f, src, e)
    })
}
