//! The rupy → WebAssembly compiler as a WebAssembly module, for browsers: the
//! translator and the wasm backend (`rupy::wasm`) built for
//! `wasm32-unknown-unknown`. `web/build.sh` builds it; `web/index.html`
//! compiles rupy programs with it and runs them with the host `rupy_wasm.mjs`.
//!
//! The interface is plain C: `alloc(n)` reserves n bytes for the source,
//! `compile(ptr, len)` returns 0 (the output is the program's wasm) or 1 (the
//! output is the error message), `out_ptr()` / `out_len()` give the output.
//! `compile_project(ptr, len)` takes JSON `{"main": PATH, "files": {PATH: TEXT}}`
//! (a program and the local modules it imports) and returns 0 (wasm) or 1 (the
//! output is JSON `{"file", "line", "msg", "hint"}`; line 0: no line).

use std::sync::Mutex;

static OUT: Mutex<Vec<u8>> = Mutex::new(Vec::new());

/// Reserve `n` bytes (for the source text); never freed (one per compile).
#[no_mangle]
pub extern "C" fn alloc(n: usize) -> *mut u8 {
    let mut v = Vec::<u8>::with_capacity(n.max(1));
    let p = v.as_mut_ptr();
    std::mem::forget(v);
    p
}

/// Compile the UTF-8 source at `ptr` → 0 (wasm) or 1 (an error message).
///
/// # Safety
/// `ptr` must point to `len` readable bytes (from `alloc`).
#[no_mangle]
pub unsafe extern "C" fn compile(ptr: *const u8, len: usize) -> i32 {
    let src = String::from_utf8_lossy(unsafe { std::slice::from_raw_parts(ptr, len) }).into_owned();
    let (code, out) = match rupy::wasm::compile_source(&src) {
        Ok(bytes) => (0, bytes),
        Err(e) => (1, e.into_bytes()),
    };
    *OUT.lock().unwrap() = out;
    code
}

/// Compile a program of several files (JSON at `ptr`) → 0 (wasm) or 1 (a JSON error).
///
/// # Safety
/// `ptr` must point to `len` readable bytes (from `alloc`).
#[no_mangle]
pub unsafe extern "C" fn compile_project(ptr: *const u8, len: usize) -> i32 {
    let input = unsafe { std::slice::from_raw_parts(ptr, len) };
    let error = |file: &str, line: u32, msg: String, hint: Option<String>| serde_json::json!({ "file": file, "line": line, "msg": msg, "hint": hint }).to_string().into_bytes();
    let (code, out) = match serde_json::from_slice::<serde_json::Value>(input) {
        Err(e) => (1, error("", 0, format!("bad project JSON: {}", e), None)),
        Ok(v) => {
            let main = v["main"].as_str().unwrap_or("main.py").to_string();
            let files = v["files"].as_object().map(|m| m.iter().filter_map(|(k, t)| Some((k.into(), t.as_str()?.to_string()))).collect()).unwrap_or_default();
            match rupy::wasm::compile_files(&main, &files) {
                Ok(bytes) => (0, bytes),
                Err(e) => (1, error(&e.file, e.line, e.msg, e.hint)),
            }
        }
    };
    *OUT.lock().unwrap() = out;
    code
}

/// The last output.
#[no_mangle]
pub extern "C" fn out_ptr() -> *const u8 {
    OUT.lock().unwrap().as_ptr()
}

/// The last output's length.
#[no_mangle]
pub extern "C" fn out_len() -> usize {
    OUT.lock().unwrap().len()
}
