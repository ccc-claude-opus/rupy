//! `enum.Enum`: a class of members becomes a frozen dataclass `C(name, value)`
//! before lowering. `C.RED` is `C("RED", 1)`, `C(1)` and `C["RED"]` look the
//! member up, and `C` as a value (`for c in C`, `len(C)`, `list(C)`) is the list
//! of members. The added code (fields, `__repr__`, `__str__`, the lookups) is
//! written after the program's text and parsed with it.

use std::cell::RefCell;
use std::collections::HashMap;

use ruff_python_ast::visitor::transformer::{self, Transformer};
use ruff_python_ast::{self as ast, Expr, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::diag::{Error, Res};

fn is_enum_base(e: &Expr, names: &[String]) -> bool {
    match e {
        Expr::Name(n) => names.iter().any(|x| x == n.id.as_str()),
        Expr::Attribute(a) => a.attr.id.as_str() == "Enum" && matches!(&*a.value, Expr::Name(m) if m.id.as_str() == "enum"),
        _ => false,
    }
}

fn line_of(lines: &ruff_source_file::LineIndex, at: TextRange) -> u32 {
    lines.line_index(at.start()).get() as u32
}

/// The new text of the program when it defines enums (`None`: no enums).
pub(super) fn expand(src: &str) -> Res<Option<String>> {
    let Ok(parsed) = ruff_python_parser::parse_module(src) else { return Ok(None) };
    let body = &parsed.syntax().body;
    let lines = ruff_source_file::LineIndex::from_source_text(src);
    // `from enum import Enum, auto` / `import enum`
    let mut enum_names: Vec<String> = vec![];
    let mut auto_names: Vec<String> = vec!["auto".into()];
    let mut module = false;
    for s in body {
        match s {
            Stmt::ImportFrom(i) if i.module.as_ref().is_some_and(|m| m.id.as_str() == "enum") => {
                for a in &i.names {
                    let local = a.asname.as_ref().unwrap_or(&a.name).id.to_string();
                    match a.name.id.as_str() {
                        "Enum" => enum_names.push(local),
                        "auto" => auto_names.push(local),
                        "unique" => {}
                        n => return Err(Error::new(line_of(&lines, s.range()), format!("enum.{} is not supported (only Enum, auto, unique)", n))),
                    }
                }
            }
            Stmt::Import(i) if i.names.iter().any(|a| a.name.id.as_str() == "enum") => module = true,
            _ => {}
        }
    }
    if enum_names.is_empty() && !module {
        return Ok(None);
    }
    let mut found = false;
    let mut snippet = String::from("\nfrom dataclasses import dataclass\n");
    for s in body {
        let Stmt::ClassDef(c) = s else { continue };
        let Some(args) = &c.arguments else { continue };
        if !args.args.iter().any(|b| is_enum_base(b, &enum_names)) {
            continue;
        }
        let name = c.name.id.to_string();
        let mut members: Vec<(String, String)> = vec![];
        let mut lookup = HashMap::new();
        let mut ty: Option<&'static str> = None;
        let mut last_int: Option<i64> = None;
        for st in &c.body {
            let Stmt::Assign(a) = st else { continue };
            let [Expr::Name(t)] = &a.targets[..] else { continue };
            let auto = matches!(&*a.value, Expr::Call(call) if matches!(&*call.func, Expr::Name(n) if auto_names.iter().any(|x| x == n.id.as_str()))
                || matches!(&*call.func, Expr::Attribute(at) if at.attr.id.as_str() == "auto"));
            let (v, vt): (String, &'static str) = if auto {
                let n = last_int.map_or(1, |x| x + 1);
                (n.to_string(), "int")
            } else {
                let text = src[a.value.range()].to_string();
                match &*a.value {
                    Expr::NumberLiteral(nl) => match &nl.value {
                        ast::Number::Int(i) => (text, if i.as_i64().is_some() { "int" } else { "" }),
                        ast::Number::Float(_) => (text, "float"),
                        _ => (text, ""),
                    },
                    Expr::UnaryOp(u) if matches!(&*u.operand, Expr::NumberLiteral(_)) => {
                        let is_int = matches!(&*u.operand, Expr::NumberLiteral(nl) if matches!(nl.value, ast::Number::Int(_)));
                        (text, if is_int { "int" } else { "float" })
                    }
                    Expr::StringLiteral(_) => (text, "str"),
                    _ => (text, ""),
                }
            };
            if vt.is_empty() {
                return Err(Error::new(line_of(&lines, st.range()), "enum values must be int, float or str literals, or auto()"));
            }
            if vt == "int" {
                last_int = v.trim().parse::<i64>().ok();
            }
            match ty {
                Some(t) if t != vt => return Err(Error::new(line_of(&lines, st.range()), format!("the values of enum `{}` must all be of one type", name))),
                _ => ty = Some(vt),
            }
            // a value seen before: an alias of that member
            let canon = members.iter().find(|(_, x)| *x == v).map(|(n, _)| n.clone());
            match canon {
                Some(first) => {
                    lookup.insert(t.id.to_string(), (first, v));
                }
                None => {
                    lookup.insert(t.id.to_string(), (t.id.to_string(), v.clone()));
                    members.push((t.id.to_string(), v));
                }
            }
        }
        let Some(ty) = ty else {
            return Err(Error::new(line_of(&lines, c.range()), format!("enum `{}` has no members", name)));
        };
        let make = |n: &str, v: &str| format!("{}({:?}, {})", name, n, v);
        snippet += &format!(
            "@dataclass(frozen=True)\nclass __enum_{n}_parts:\n    name: str\n    value: {t}\n\n    def __repr__(self) -> str:\n        return \"<{n}.\" + self.name + \": \" + repr(self.value) + \">\"\n\n    def __str__(self) -> str:\n        return \"{n}.\" + self.name\n\n",
            n = name,
            t = ty
        );
        snippet += &format!("def __enum_{n}_value(v: {t}) -> {n}:\n", n = name, t = ty);
        for (m, v) in &members {
            snippet += &format!("    if v == {}:\n        return {}\n", v, make(m, v));
        }
        snippet += &format!("    raise ValueError(repr(v) + \" is not a valid {}\")\n\n", name);
        snippet += &format!("def __enum_{n}_name(k: str) -> {n}:\n", n = name);
        for (m, (first, v)) in &lookup {
            snippet += &format!("    if k == {:?}:\n        return {}\n", m, make(first, v));
        }
        snippet += "    raise KeyError(k)\n\n";
        snippet += &format!(
            "def __enum_{n}_members() -> list[{n}]:\n    return [{}]\n\n",
            members.iter().map(|(m, v)| make(m, v)).collect::<Vec<_>>().join(", "),
            n = name
        );
        found = true;
    }
    if !found {
        return Ok(None);
    }
    Ok(Some(format!("{}\n{}", src, snippet)))
}

/// After `expand`: the enum classes get the dataclass parts, and the uses of
/// enums become the generated code. `body` is the parsed new text.
pub(super) fn rewrite(module: &mut ast::ModModule, src: &str, lines: &ruff_source_file::LineIndex) -> Res<()> {
    let body = &mut module.body;
    // the enums and their parts
    let mut parts: HashMap<String, ast::StmtClassDef> = HashMap::new();
    body.retain(|s| match s {
        Stmt::ClassDef(c) if c.name.id.starts_with("__enum_") && c.name.id.ends_with("_parts") => {
            let n = c.name.id.trim_start_matches("__enum_").trim_end_matches("_parts").to_string();
            parts.insert(n, c.clone());
            false
        }
        _ => true,
    });
    let mut enums: HashMap<String, HashMap<String, (String, String)>> = HashMap::new();
    for s in body.iter_mut() {
        let Stmt::ClassDef(c) = s else { continue };
        let Some(p) = parts.remove(c.name.id.as_str()) else { continue };
        let mut lookup = HashMap::new();
        let mut kept: Vec<Stmt> = p.body.iter().filter(|x| matches!(x, Stmt::AnnAssign(_))).cloned().collect();
        for st in c.body.iter() {
            match st {
                Stmt::Assign(a) if matches!(&a.targets[..], [Expr::Name(_)]) => {
                    let Expr::Name(t) = &a.targets[0] else { unreachable!() };
                    lookup.insert(t.id.to_string(), (String::new(), src[a.value.range()].to_string()));
                }
                Stmt::Pass(_) => {}
                Stmt::Expr(e) if matches!(&*e.value, Expr::StringLiteral(_)) => {}
                x => kept.push(x.clone()),
            }
        }
        kept.extend(p.body.iter().filter(|x| matches!(x, Stmt::FunctionDef(_))).cloned());
        c.body = kept.into_iter().collect();
        c.decorator_list = p.decorator_list.clone();
        c.arguments = None;
        enums.insert(c.name.id.to_string(), lookup);
    }
    let r = Rewriter { src, enums: &enums, lines, err: RefCell::new(None) };
    for s in body.iter_mut() {
        r.visit_stmt(s);
    }
    // the enum imports
    body.retain(|s| !matches!(s, Stmt::ImportFrom(i) if i.module.as_ref().is_some_and(|m| m.id.as_str() == "enum")) && !matches!(s, Stmt::Import(i) if i.names.iter().all(|a| a.name.id.as_str() == "enum")));
    match r.err.into_inner() {
        Some(e) => Err(e),
        None => Ok(()),
    }
}

struct Rewriter<'s> {
    src: &'s str,
    /// enum → its member names (values unused here: the generated lookups know them)
    enums: &'s HashMap<String, HashMap<String, (String, String)>>,
    lines: &'s ruff_source_file::LineIndex,
    err: RefCell<Option<Error>>,
}

impl Rewriter<'_> {
    fn enum_name(&self, e: &Expr) -> Option<String> {
        match e {
            Expr::Name(n) if self.enums.contains_key(n.id.as_str()) => Some(n.id.to_string()),
            _ => None,
        }
    }

    fn replace(&self, e: &mut Expr, code: String) {
        let at = e.range();
        match ruff_python_parser::parse_expression(&code) {
            Ok(p) => {
                let mut new = p.into_expr();
                let inner = Rewriter { src: &code, enums: self.enums, lines: self.lines, err: RefCell::new(None) };
                inner.visit_expr(&mut new);
                if let Some(x) = inner.err.into_inner() {
                    self.err.borrow_mut().get_or_insert(x);
                }
                ruff_python_ast::relocate::relocate_expr(&mut new, at);
                *e = new;
            }
            Err(_) => {
                let line = self.lines.line_index(at.start()).get() as u32;
                self.err.borrow_mut().get_or_insert(Error::new(line, "this use of an enum is not supported"));
            }
        }
    }
}

impl Transformer for Rewriter<'_> {
    // `x: Color` stays the class
    fn visit_annotation(&self, _: &mut Expr) {}

    fn visit_expr(&self, e: &mut Expr) {
        match e {
            // Color.RED → the member (Color.RED.name: the member's name)
            Expr::Attribute(a) => {
                if let Some(n) = self.enum_name(&a.value) {
                    if self.enums[&n].contains_key(a.attr.id.as_str()) {
                        let code = format!("__enum_{}_name({:?})", n, a.attr.id.as_str());
                        self.replace(e, code);
                        return;
                    }
                    // Color.name() style methods of the class itself are not members
                    return;
                }
            }
            // Color(1) → by value
            Expr::Call(c) => {
                if let Some(n) = self.enum_name(&c.func) {
                    if let [arg] = &c.arguments.args[..] {
                        if c.arguments.keywords.is_empty() {
                            let code = format!("__enum_{}_value({})", n, &self.src[arg.range()]);
                            self.replace(e, code);
                            return;
                        }
                    }
                    // the dataclass's own constructor (generated code)
                    if let Expr::Call(c) = e {
                        self.visit_arguments(&mut c.arguments);
                    }
                    return;
                }
                if matches!(&*c.func, Expr::Name(f) if f.id.as_str() == "isinstance") {
                    return;
                }
            }
            // Color["RED"] → by name
            Expr::Subscript(s) => {
                if let Some(n) = self.enum_name(&s.value) {
                    let code = format!("__enum_{}_name({})", n, &self.src[s.slice.range()]);
                    self.replace(e, code);
                    return;
                }
            }
            // Color as a value → its members
            Expr::Name(x) if x.ctx == ast::ExprContext::Load && self.enums.contains_key(x.id.as_str()) => {
                let code = format!("__enum_{}_members()", x.id.as_str());
                self.replace(e, code);
                return;
            }
            _ => {}
        }
        transformer::walk_expr(self, e);
    }
}
