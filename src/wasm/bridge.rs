//! The bridge between the wasm backend and the packages implemented in Rust
//! (numpy, sklearn, torch, ...).
//!
//! The packages are compiled once, by cargo, to their own wasm module,
//! `rupy_lib.wasm` (`rupy wasm-lib`). A compiled program holds no package
//! code: each package function it calls becomes a small function that sends
//! the arguments to the host as a list of tokens (ints, floats, strings; a
//! list is its length then its items, an optional value a 0 / 1 flag then the
//! value, a package object the number of its handle) and reads the result
//! back the same way. The host passes the tokens to `rupy_lib.wasm`, whose
//! dispatcher (generated here, from the package stubs) decodes them, calls the
//! package, and encodes the result; package objects stay in its memory, in a
//! table of handles.
//!
//! The dispatcher calls wrappers that rupy itself translates from Python:
//! for each package function, `def w_N(params) -> ret: return M.f(params)`,
//! so the Rust call (borrowing, conversions, templates of the stub) is the one
//! a translated program would make. Each function is identified by its [`key`].

use crate::ir::*;
use std::collections::HashMap;
use std::fmt::Write;

/// The packages in `rupy_lib.wasm`: (module, cargo feature).
pub const LIB_MODULES: &[(&str, &str)] = &[
    ("numpy", "numpy"),
    ("sklearn.cluster", "sklearn"),
    ("sklearn.datasets", "sklearn"),
    ("sklearn.decomposition", "sklearn"),
    ("sklearn.linear_model", "sklearn"),
    ("sklearn.metrics", "sklearn"),
    ("sklearn.model_selection", "sklearn"),
    ("sklearn.naive_bayes", "sklearn"),
    ("sklearn.neighbors", "sklearn"),
    ("sklearn.preprocessing", "sklearn"),
    ("gymnasium", "gymnasium"),
    ("torch", "torch"),
    ("torch.nn", "torch"),
    ("torch.nn.functional", "torch"),
    ("torch.optim", "torch"),
    ("rupy.json", ""),
    ("shlex", ""),
    ("fnmatch", ""),
    ("html", ""),
];

/// The runtime features of a program's packages that `rupy_lib.wasm` has.
pub fn lib_has(feature: &str) -> bool {
    matches!(feature, "pyrt/numpy" | "pyrt/sklearn" | "pyrt/gymnasium" | "pyrt/torch")
}

/// The name the bridge knows package function `f` by: its class, name, Rust
/// path or template, and parameter types (overloads differ in them).
pub fn key(p: &Program, f: FuncId) -> String {
    let func = &p.funcs[f];
    let class = func.class.and_then(|c| p.classes[c].ext.clone()).unwrap_or_default();
    let rust = func.ext.as_ref().map(|x| x.rust.as_str()).unwrap_or("");
    let params: Vec<String> = func.params.iter().map(|pa| TyName(&func.vars[pa.var].ty, p).to_string()).collect();
    format!("{}|{}|{}|{}", class, func.name, rust, params.join(","))
}

/// The key of a numpy-style index (`a[1:, 0]`), built by the dispatcher too.
pub const INDEX_KEY: &str = "@index";

/// Whether values of type `t` cross the bridge.
pub fn bridged(t: &Ty, p: &Program) -> bool {
    match t {
        Ty::Int | Ty::Float | Ty::Bool | Ty::Str | Ty::None => true,
        Ty::List(e) | Ty::Optional(e) => bridged(e, p),
        Ty::Tuple(ts) => ts.iter().all(|t| bridged(t, p)),
        Ty::Class(c) | Ty::Obj(c) => p.classes[*c].ext.is_some(),
        _ => false,
    }
}

/// Whether results of type `t` cross the bridge (also dicts, which arguments cannot be).
pub fn bridged_result(t: &Ty, p: &Program) -> bool {
    match t {
        Ty::Dict(k, v, DK::Plain) => matches!(**k, Ty::Str | Ty::Int) && bridged_result(v, p),
        Ty::List(e) | Ty::Optional(e) => bridged_result(e, p),
        Ty::Tuple(ts) => ts.iter().all(|t| bridged_result(t, p)),
        t => bridged(t, p),
    }
}

/// One package function to wrap.
struct Spec {
    key: String,
    /// `(name, type)`, the receiver first for a method
    params: Vec<(String, Ty)>,
    ret: Ty,
    /// call forms to try: the expression in `w_N`
    calls: Vec<String>,
    /// a Rust function called directly, without a wrapper (a `*args`
    /// function: Python has no call that passes a list to it)
    direct: Option<String>,
}

/// The generated sources of the dispatcher crate.
pub struct LibSources {
    /// `wrappers.rs`: the translated wrappers
    pub wrappers: String,
    /// `dispatch.rs`: `fn dispatch(key, ...)`
    pub dispatch: String,
    /// the cargo features of rupy it needs
    pub features: Vec<String>,
    /// package functions left out, with the reason
    pub skipped: Vec<String>,
}

/// Generate the dispatcher of [`LIB_MODULES`].
pub fn generate() -> Result<LibSources, String> {
    let aliases: Vec<String> = (0..LIB_MODULES.len()).map(|i| format!("M{}", i)).collect();
    let imports: String = LIB_MODULES.iter().zip(&aliases).map(|((m, _), a)| format!("import {} as {}\n", m, a)).collect();
    // where each class and top-level function is declared
    let mut class_home: HashMap<String, (usize, String)> = HashMap::new();
    let mut func_home: HashMap<String, usize> = HashMap::new();
    for (i, (m, _)) in LIB_MODULES.iter().enumerate() {
        let text = stub_text(m).ok_or_else(|| format!("no stub for {}", m))?;
        let p = crate::front::lower(&format!("import {} as A\n", m)).map_err(|e| format!("{}: {}", m, e.msg))?;
        for c in &p.classes {
            if let Some(ext) = &c.ext {
                let declared = text.contains(&format!("\nclass {}:", c.name)) || text.contains(&format!("\nclass {}(", c.name));
                if declared {
                    class_home.entry(ext.clone()).or_insert((i, c.name.clone()));
                }
            }
        }
        for f in 0..p.funcs.len() {
            if p.funcs[f].ext.is_some() && p.funcs[f].class.is_none() {
                func_home.entry(key(&p, f)).or_insert(i);
            }
        }
    }
    let p = crate::front::lower(&imports).map_err(|e| e.msg)?;
    let mut skipped = vec![];
    let mut specs: Vec<Spec> = vec![];
    let mut seen = std::collections::HashSet::new();
    for fid in 0..p.funcs.len() {
        let f = &p.funcs[fid];
        if f.ext.is_none() {
            continue;
        }
        let k = key(&p, fid);
        if !seen.insert(k.clone()) {
            continue;
        }
        let ann = |t: &Ty| py_type(t, &p, &class_home, &aliases);
        let mut params: Vec<(String, Ty)> = vec![];
        let method = f.class.is_some() && !f.is_static && f.self_var.is_some() && !f.is_init;
        if method {
            let c = f.class.unwrap();
            params.push(("s".into(), Ty::Class(c)));
        }
        for (i, pa) in f.params.iter().enumerate() {
            params.push((format!("a{}", i), f.vars[pa.var].ty.clone()));
        }
        let ret = if f.is_init { Ty::Class(f.class.unwrap()) } else { f.ret.clone() };
        if let Some((_, t)) = params.iter().find(|(_, t)| !bridged(t, &p) || ann(t).is_none()) {
            skipped.push(format!("{}: a parameter of type {}", k, TyName(t, &p)));
            continue;
        }
        if !bridged_result(&ret, &p) || ann(&ret).is_none() {
            skipped.push(format!("{}: returns {}", k, TyName(&ret, &p)));
            continue;
        }
        // the Python expression of the call, in several argument forms
        let names: Vec<String> = f.params.iter().map(|pa| f.vars[pa.var].name.clone()).collect();
        let n = names.len();
        let forms: Vec<String> = (0..=n)
            .rev()
            .map(|k| {
                (0..n)
                    .map(|i| if i < k { format!("a{}", i) } else { format!("{}=a{}", names[i], i) })
                    .collect::<Vec<_>>()
                    .join(", ")
            })
            .collect();
        let target = if method {
            format!("s.{}", f.name)
        } else if let Some(c) = f.class {
            let Some((m, cname)) = p.classes[c].ext.as_ref().and_then(|e| class_home.get(e)) else {
                skipped.push(format!("{}: its class is not declared by a package", k));
                continue;
            };
            if f.is_init {
                format!("{}.{}", aliases[*m], cname)
            } else {
                format!("{}.{}.{}", aliases[*m], cname, f.name)
            }
        } else {
            let Some(m) = func_home.get(&k) else {
                skipped.push(format!("{}: not declared by a package", k));
                continue;
            };
            format!("{}.{}", aliases[*m], f.name)
        };
        let calls = if f.property { vec![target] } else { forms.iter().map(|a| format!("{}({})", target, a)).collect() };
        let ext = f.ext.as_ref().unwrap();
        let direct = (f.varargs.is_some() && !ext.rust.contains('{') && !ext.result).then(|| ext.rust.clone());
        if f.varargs.is_some() && direct.is_none() {
            skipped.push(format!("{}: *args", k));
            continue;
        }
        specs.push(Spec { key: k, params, ret, calls, direct });
    }
    // the wrappers: translate, and drop (or try the next call form of) the
    // wrapper of each line the translator rejects
    let mut form = vec![0usize; specs.len()];
    let mut live = vec![true; specs.len()];
    let rust = loop {
        let (src, lines) = wrapper_source(&imports, &specs, &form, &live, &p, &class_home, &aliases);
        match crate::translate(&src) {
            Ok(r) => break r,
            Err(e) => {
                let Some(i) = lines.iter().position(|&(lo, hi)| e.line >= lo && e.line <= hi) else {
                    return Err(format!("the wrappers do not translate: line {}: {}\n{}", e.line, e.msg, numbered(&src, e.line)));
                };
                // a caller's line points at its wrapper too
                form[i] += 1;
                if form[i] >= specs[i].calls.len() {
                    live[i] = false;
                    skipped.push(format!("{}: {}", specs[i].key, e.msg));
                }
            }
        }
    };
    let wrappers = module_text(&rust);
    let sigs = signatures(&wrappers);
    let mut dispatch = String::from(
        "// @generated by `rupy wasm-lib`: the dispatcher of rupy_lib.wasm.\n\n\
         #[allow(unused_variables, unused_mut, unused_parens, clippy::all)]\n\
         pub fn dispatch(key: &str, d: &mut Dec, e: &mut Enc, h: &mut Handles) -> Result<(), PyErr> {\n    match key {\n",
    );
    for (i, s) in specs.iter().enumerate() {
        if !live[i] {
            continue;
        }
        if let Some(path) = &s.direct {
            // lists by reference, the rest by value
            let ptys: Vec<String> = s.params.iter().map(|(_, t)| if matches!(t, Ty::List(_)) { "&".to_string() } else { String::new() }).collect();
            dispatch += &arm(i, s, &ptys, false, &p, &class_home).replace(&format!("crate::wrappers::w_{}(", i), &format!("{}(", path));
            continue;
        }
        let Some((ptys, result)) = sigs.get(&format!("w_{}", i)) else {
            return Err(format!("no signature for w_{}", i));
        };
        dispatch += &arm(i, s, ptys, *result, &p, &class_home);
    }
    dispatch += &format!("        {:?} => index(d, e, h),\n", INDEX_KEY);
    // the classes whose objects cross the bridge (an array may be an index)
    let mut objs: Vec<String> = vec![];
    for (i, s) in specs.iter().enumerate() {
        if live[i] {
            for t in s.params.iter().map(|(_, t)| t).chain(std::iter::once(&s.ret)) {
                classes_in(t, &p, &mut objs);
            }
        }
    }
    objs.sort();
    objs.dedup();
    dispatch += "        _ => Err(PyErr::new(&[\"NotImplementedError\", \"RuntimeError\", \"Exception\", \"BaseException\"], &format!(\"rupy_lib.wasm has no `{}`\", key))),\n    }\n}\n";
    dispatch += "\n/// An object used as an index part.\nfn index_obj(h: &Handles, id: i64) -> Result<rupy::pyrt::Ix, PyErr> {\n";
    for o in &objs {
        if o != "rupy::pyrt::Index" {
            dispatch += &format!("    if let Ok(x) = h.get::<{}>(id) {{\n        return Ok(rupy::pyrt::Ix::obj(x.clone()));\n    }}\n", o);
        }
    }
    dispatch += "    Err(PyErr::new(&[\"IndexError\", \"LookupError\", \"Exception\", \"BaseException\"], \"rupy_lib: this object is not an index\"))\n}\n";
    let mut features: Vec<String> = LIB_MODULES.iter().map(|(_, f)| f.to_string()).filter(|f| !f.is_empty()).collect();
    features.push("re".into());
    features.sort();
    features.dedup();
    Ok(LibSources { wrappers, dispatch, features, skipped })
}

fn numbered(src: &str, line: u32) -> String {
    src.lines().enumerate().skip((line as usize).saturating_sub(4)).take(7).map(|(i, l)| format!("{:5} {}\n", i + 1, l)).collect()
}

/// The stub text of a package (a file, or the copy built into rupy).
fn stub_text(module: &str) -> Option<String> {
    crate::front::package_stub_text(module)
}

/// The Python annotation of `t` in the wrapper module.
fn py_type(t: &Ty, p: &Program, home: &HashMap<String, (usize, String)>, aliases: &[String]) -> Option<String> {
    Some(match t {
        Ty::Int => "int".into(),
        Ty::Float => "float".into(),
        Ty::Bool => "bool".into(),
        Ty::Str => "str".into(),
        Ty::None => "None".into(),
        Ty::List(e) => format!("list[{}]", py_type(e, p, home, aliases)?),
        Ty::Optional(e) => format!("{} | None", py_type(e, p, home, aliases)?),
        Ty::Tuple(ts) => {
            let parts: Option<Vec<String>> = ts.iter().map(|t| py_type(t, p, home, aliases)).collect();
            format!("tuple[{}]", parts?.join(", "))
        }
        Ty::Dict(k, v, DK::Plain) => format!("dict[{}, {}]", py_type(k, p, home, aliases)?, py_type(v, p, home, aliases)?),
        Ty::Class(c) | Ty::Obj(c) => {
            let (m, name) = home.get(p.classes[*c].ext.as_ref()?)?;
            format!("{}.{}", aliases[*m], name)
        }
        _ => return None,
    })
}

/// The wrapper module, and the line range of each wrapper (and its caller).
fn wrapper_source(
    imports: &str,
    specs: &[Spec],
    form: &[usize],
    live: &[bool],
    p: &Program,
    home: &HashMap<String, (usize, String)>,
    aliases: &[String],
) -> (String, Vec<(u32, u32)>) {
    let mut src = imports.to_string();
    let mut lines = vec![(0, 0); specs.len()];
    let line = |s: &String| s.lines().count() as u32 + 1;
    for (i, s) in specs.iter().enumerate() {
        if !live[i] || s.direct.is_some() {
            continue;
        }
        let ps: Vec<String> = s.params.iter().map(|(n, t)| format!("{}: {}", n, py_type(t, p, home, aliases).unwrap())).collect();
        let ret = py_type(&s.ret, p, home, aliases).unwrap();
        let lo = line(&src) + 2;
        let call = &s.calls[form[i]];
        let body = if s.ret == Ty::None { format!("    {}\n", call) } else { format!("    return {}\n", call) };
        let _ = write!(src, "\n\ndef w_{}({}) -> {}:\n{}", i, ps.join(", "), ret, body);
        // a caller that catches: the wrapper returns its exceptions as `Err`
        let args: Vec<&str> = s.params.iter().map(|(n, _)| n.as_str()).collect();
        let _ = write!(src, "\n\ndef c_{}({}) -> None:\n    try:\n        w_{}({})\n    except Exception:\n        pass\n", i, ps.join(", "), i, args.join(", "));
        lines[i] = (lo, line(&src));
    }
    (src, lines)
}

/// The translated wrappers as a module of the dispatcher crate.
fn module_text(rust: &str) -> String {
    let mut out = String::from("// @generated by `rupy wasm-lib`: the package wrappers of rupy_lib.wasm.\n#![allow(clippy::all, unused, dead_code, non_snake_case, unused_imports)]\n");
    let mut skip_main = false;
    for line in rust.lines() {
        if line.starts_with("#![allow(") || line.starts_with("// some definitions are not used") {
            continue;
        }
        if line == "fn main() {" {
            skip_main = true;
        }
        if skip_main {
            if line == "}" {
                skip_main = false;
            }
            continue;
        }
        if let Some(rest) = line.strip_prefix("fn w_") {
            out += "pub fn w_";
            out += rest;
        } else {
            out += line;
        }
        out.push('\n');
    }
    out
}

/// `w_N` → (Rust parameter types, returns `Result`).
fn signatures(rust: &str) -> HashMap<String, (Vec<String>, bool)> {
    let mut m = HashMap::new();
    for line in rust.lines() {
        let Some(rest) = line.strip_prefix("pub fn ") else { continue };
        let Some(open) = rest.find('(') else { continue };
        let name = rest[..open].to_string();
        // the parameter list: up to the matching parenthesis
        let mut depth = 0;
        let mut close = open;
        for (i, ch) in rest.char_indices().skip(open) {
            match ch {
                '(' | '<' | '[' => depth += 1,
                ')' | '>' | ']' => {
                    depth -= 1;
                    if depth == 0 && ch == ')' {
                        close = i;
                        break;
                    }
                }
                _ => {}
            }
        }
        let params = split_top(&rest[open + 1..close]).into_iter().map(|p| p.split_once(": ").map(|(_, t)| t.trim().to_string()).unwrap_or_default()).collect();
        let result = rest[close..].contains("-> Result<");
        m.insert(name, (params, result));
    }
    m
}

/// Split at commas outside brackets.
fn split_top(s: &str) -> Vec<String> {
    let (mut out, mut cur, mut depth) = (vec![], String::new(), 0);
    for ch in s.chars() {
        match ch {
            '(' | '<' | '[' => depth += 1,
            ')' | '>' | ']' => depth -= 1,
            ',' if depth == 0 => {
                out.push(std::mem::take(&mut cur));
                continue;
            }
            _ => {}
        }
        cur.push(ch);
    }
    if !cur.trim().is_empty() {
        out.push(cur);
    }
    out
}

/// The package classes in `t`.
fn classes_in(t: &Ty, p: &Program, out: &mut Vec<String>) {
    match t {
        Ty::List(e) | Ty::Optional(e) => classes_in(e, p, out),
        Ty::Tuple(ts) => ts.iter().for_each(|t| classes_in(t, p, out)),
        Ty::Class(c) | Ty::Obj(c) => out.extend(p.classes[*c].ext.clone()),
        _ => {}
    }
}

/// The source of the dispatcher crate's `lib.rs` (handles, tokens, exports).
pub const LIB_RT: &str = include_str!("lib_rt.rs.in");

/// The Rust type of a package class.
fn rust_class(c: ClassId, p: &Program) -> String {
    p.classes[c].ext.clone().unwrap_or_default()
}

/// Rust code decoding a `t` from `d` (an owned value).
fn decode(t: &Ty, p: &Program) -> String {
    match t {
        Ty::Int => "d.int()?".into(),
        Ty::Float => "d.float()?".into(),
        Ty::Bool => "(d.int()? != 0)".into(),
        Ty::Str => "d.str()?".into(),
        Ty::None => "()".into(),
        Ty::List(e) => format!("{{ let n = d.int()? as usize; let mut v = Vec::with_capacity(n); for _ in 0..n {{ v.push({}); }} v }}", decode(e, p)),
        Ty::Optional(e) => format!("(if d.int()? != 0 {{ Some({}) }} else {{ None }})", decode(e, p)),
        Ty::Tuple(ts) => format!("({},)", ts.iter().map(|t| decode(t, p)).collect::<Vec<_>>().join(", ")),
        Ty::Class(c) | Ty::Obj(c) => format!("h.get::<{}>(d.int()?)?.clone()", rust_class(*c, p)),
        _ => unreachable!(),
    }
}

/// Rust code encoding the value `x` of type `t` into `e`.
fn encode(x: &str, t: &Ty, p: &Program, n: &mut usize) -> String {
    *n += 1;
    let v = format!("v{}", n);
    match t {
        Ty::Int => format!("e.int({} as i64);", x),
        Ty::Float => format!("e.float({} as f64);", x),
        Ty::Bool => format!("e.int({} as i64);", x),
        Ty::Str => format!("e.str(&{});", x),
        Ty::None => format!("let _ = {};", x),
        Ty::List(el) => format!("{{ let l = {}; e.int(l.len() as i64); for {} in l {{ {} }} }}", x, v, encode(&v, el, p, n)),
        Ty::Optional(el) => format!("match {} {{ Some({}) => {{ e.int(1); {} }} None => e.int(0) }}", x, v, encode(&v, el, p, n)),
        Ty::Tuple(ts) => {
            let names: Vec<String> = (0..ts.len()).map(|i| format!("{}_{}", v, i)).collect();
            let mut s = format!("{{ let ({},) = {}; ", names.join(", "), x);
            for (nm, t) in names.iter().zip(ts) {
                s += &encode(nm, t, p, n);
                s.push(' ');
            }
            s + "}"
        }
        Ty::Class(_) | Ty::Obj(_) => format!("e.int(h.put({}));", x),
        Ty::Dict(kt, vt, _) => {
            let (k, vv) = (format!("{}k", v), format!("{}v", v));
            format!("{{ let m = {}; e.int(m.len() as i64); for ({}, {}) in m {{ {} {} }} }}", x, k, vv, encode(&k, kt, p, n), encode(&vv, vt, p, n))
        }
        _ => unreachable!(),
    }
}

/// The dispatcher arm of wrapper `i`.
fn arm(i: usize, s: &Spec, ptys: &[String], result: bool, p: &Program, _home: &HashMap<String, (usize, String)>) -> String {
    // package objects: `&` borrows the one in the table (its state may be
    // interior, like a fitted model's), `&mut` takes it out and puts it back,
    // by value is a copy
    let mut code = format!("        {:?} => {{\n", s.key);
    let (mut args, mut gets, mut takes, mut back) = (vec![], String::new(), String::new(), String::new());
    for (j, (_, t)) in s.params.iter().enumerate() {
        let rt = ptys.get(j).map(String::as_str).unwrap_or("");
        if let Ty::Class(c) | Ty::Obj(c) = t {
            let ty = rust_class(*c, p);
            code += &format!("            let id{} = d.int()?;\n", j);
            if rt.starts_with("&mut ") {
                takes += &format!("            let mut p{}: {} = h.take::<{}>(id{})?;\n", j, ty, ty, j);
                back += &format!("            h.set(id{}, p{});\n", j, j);
                args.push(format!("&mut p{}", j));
            } else if rt.starts_with('&') {
                gets += &format!("                let p{}: &{} = h.get::<{}>(id{})?;\n", j, ty, ty, j);
                args.push(format!("p{}", j));
            } else {
                gets += &format!("                let p{}: {} = h.get::<{}>(id{})?.clone();\n", j, ty, ty, j);
                args.push(format!("p{}", j));
            }
        } else {
            code += &format!("            let mut p{} = {};\n", j, decode(t, p));
            args.push(if rt.starts_with("&mut ") {
                format!("&mut p{}", j)
            } else if rt.starts_with('&') {
                format!("&p{}", j)
            } else {
                format!("p{}", j)
            });
        }
    }
    code += &takes;
    code += &format!(
        "            let r = (|| -> Result<_, PyErr> {{\n{}                Ok(crate::wrappers::w_{}({}){})\n            }})();\n",
        gets,
        i,
        args.join(", "),
        if result { "?" } else { "" }
    );
    code += &back;
    let mut n = 0;
    code += &format!("            let r = r?;\n            {}\n            Ok(())\n        }}\n", encode("r", &s.ret, p, &mut n));
    code
}
