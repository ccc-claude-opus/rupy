//! `argparse`: `args = parser.parse_args()` has attributes Python makes at run
//! time; rupy needs their types. Before the packages are joined (`modules`),
//! each `parser.add_argument(...)` (literal arguments) becomes a call of the
//! `argparse` package's `_add`, and `parser.parse_args(...)` becomes a
//! function that turns the strings the package read into a dataclass with a
//! typed field per argument (`int` for `type=int`, `bool` for `store_true`,
//! `list[str]` for `nargs="*"`, `T | None` when it may be missing). The
//! dataclass and the function are written after the program.

use std::collections::HashMap;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{self as ast, Expr, Stmt};
use ruff_text_size::{Ranged, TextRange};

/// One `add_argument`.
struct Arg {
    dest: String,
    action: String,
    conv: String,
    nargs: String,
    positional: bool,
    required: bool,
    /// the default's source text, if given
    default: Option<String>,
}

struct Parser {
    var: String,
    args: Vec<Arg>,
}

struct Scan<'a> {
    src: &'a str,
    /// names of the module (`import argparse [as ap]`) and of the class
    modules: Vec<String>,
    classes: Vec<String>,
    parsers: Vec<Parser>,
    edits: Vec<(TextRange, String)>,
    err: Option<(TextRange, String)>,
}

fn lit_str(e: &Expr) -> Option<String> {
    match e {
        Expr::StringLiteral(s) => Some(s.value.to_str().to_string()),
        _ => None,
    }
}

impl Scan<'_> {
    fn fail(&mut self, r: TextRange, m: impl Into<String>) {
        if self.err.is_none() {
            self.err = Some((r, m.into()));
        }
    }

    fn is_parser_ctor(&self, f: &Expr) -> bool {
        match f {
            Expr::Attribute(a) => a.attr.id.as_str() == "ArgumentParser" && matches!(&*a.value, Expr::Name(m) if self.modules.iter().any(|x| x == m.id.as_str())),
            Expr::Name(n) => self.classes.iter().any(|x| x == n.id.as_str()),
            _ => false,
        }
    }

    fn parser_of(&self, e: &Expr) -> Option<usize> {
        match e {
            Expr::Name(n) => self.parsers.iter().rposition(|p| p.var == n.id.as_str()),
            _ => None,
        }
    }

    /// The text that replaces `call` (keeping its newlines: lines stay where they are).
    fn keep_lines(&self, call: TextRange, new: String) -> String {
        let n = self.src[call].matches('\n').count();
        if n == 0 {
            return new;
        }
        // newlines inside the closing parenthesis
        let (head, tail) = new.split_at(new.len() - 1);
        format!("{}{}{}", head, "\n".repeat(n), tail)
    }

    fn add_argument(&mut self, pi: usize, c: &ast::ExprCall) {
        let at = c.range();
        let mut names = vec![];
        for a in c.arguments.args.iter() {
            match lit_str(a) {
                Some(s) => names.push(s),
                None => return self.fail(a.range(), "add_argument() needs its names as string literals"),
            }
        }
        if names.is_empty() {
            return self.fail(at, "add_argument() needs a name");
        }
        let positional = !names[0].starts_with('-');
        let mut kw: HashMap<String, &Expr> = HashMap::new();
        for k in c.arguments.keywords.iter() {
            let Some(n) = &k.arg else { return self.fail(k.range(), "add_argument(**kwargs) is not supported") };
            kw.insert(n.id.to_string(), &k.value);
        }
        for k in kw.keys() {
            if !["type", "default", "help", "action", "nargs", "choices", "required", "dest", "metavar"].contains(&k.as_str()) {
                return self.fail(at, format!("add_argument({}=...) is not supported", k));
            }
        }
        let text = |e: &Expr| self.src[e.range()].to_string();
        let action = match kw.get("action") {
            None => "store".to_string(),
            Some(e) => match lit_str(e) {
                Some(a) if ["store", "store_true", "store_false", "count", "append"].contains(&a.as_str()) => a,
                _ => return self.fail(e.range(), "action= is \"store\", \"store_true\", \"store_false\", \"count\" or \"append\""),
            },
        };
        let conv = match kw.get("type") {
            None => "str".to_string(),
            Some(Expr::Name(n)) if ["int", "float", "str"].contains(&n.id.as_str()) => n.id.to_string(),
            Some(e) => return self.fail(e.range(), "type= is int, float or str"),
        };
        let nargs = match kw.get("nargs") {
            None => String::new(),
            Some(e) => match (lit_str(e), e) {
                (Some(s), _) if ["?", "*", "+"].contains(&s.as_str()) => s,
                (None, Expr::NumberLiteral(_)) => text(e),
                _ => return self.fail(e.range(), "nargs= is \"?\", \"*\", \"+\" or a number"),
            },
        };
        let dest = match kw.get("dest").map(|e| lit_str(e)) {
            Some(Some(d)) => d,
            Some(None) => return self.fail(at, "dest= needs a string literal"),
            None if positional => names[0].clone(),
            None => {
                let long = names.iter().find(|n| n.starts_with("--")).unwrap_or(&names[0]);
                long.trim_start_matches('-').replace('-', "_")
            }
        };
        if !dest.chars().all(|c| c.is_alphanumeric() || c == '_') || dest.chars().next().is_some_and(|c| c.is_ascii_digit()) {
            return self.fail(at, format!("`{}` is not a name: rupy's arguments are attributes", dest));
        }
        let required = match kw.get("required") {
            None => false,
            Some(Expr::BooleanLiteral(b)) => b.value,
            Some(e) => return self.fail(e.range(), "required= needs True or False"),
        };
        let default = kw.get("default").map(|e| text(e));
        let help = kw.get("help").map(|e| text(e)).unwrap_or_else(|| "\"\"".into());
        let metavar = kw.get("metavar").map(|e| text(e)).unwrap_or_else(|| "\"\"".into());
        let choices = match kw.get("choices") {
            None => "[]".to_string(),
            Some(Expr::List(l)) => format!("[{}]", l.elts.iter().map(|x| format!("str({})", text(x))).collect::<Vec<_>>().join(", ")),
            Some(Expr::Tuple(l)) => format!("[{}]", l.elts.iter().map(|x| format!("str({})", text(x))).collect::<Vec<_>>().join(", ")),
            Some(e) => return self.fail(e.range(), "choices= needs a list literal"),
        };
        let default_text = match &default {
            Some(d) => format!("str({})", d),
            None if action == "store_true" => "\"False\"".into(),
            None if action == "store_false" => "\"True\"".into(),
            None => "\"None\"".into(),
        };
        let var = self.parsers[pi].var.clone();
        let call = format!(
            "{}._add([{}], {:?}, {:?}, {:?}, {:?}, {}, {}, {}, {}, {})",
            var,
            names.iter().map(|n| format!("{:?}", n)).collect::<Vec<_>>().join(", "),
            dest,
            action,
            conv,
            nargs,
            choices,
            if required { "True" } else { "False" },
            help,
            metavar,
            default_text
        );
        let call = self.keep_lines(at, call);
        self.edits.push((at, call));
        self.parsers[pi].args.push(Arg { dest, action, conv, nargs, positional, required, default });
    }
}

impl<'a> Visitor<'a> for Scan<'_> {
    fn visit_stmt(&mut self, s: &'a Stmt) {
        if let Stmt::Assign(a) = s {
            if let ([Expr::Name(t)], Expr::Call(c)) = (&a.targets[..], &*a.value) {
                if self.is_parser_ctor(&c.func) {
                    self.parsers.push(Parser { var: t.id.to_string(), args: vec![] });
                }
            }
        }
        if let Stmt::Expr(e) = s {
            if let Expr::Call(c) = &*e.value {
                if let Expr::Attribute(at) = &*c.func {
                    if at.attr.id.as_str() == "add_argument" {
                        if let Some(pi) = self.parser_of(&at.value) {
                            self.add_argument(pi, c);
                            return;
                        }
                    }
                }
            }
        }
        visitor::walk_stmt(self, s);
    }

    fn visit_expr(&mut self, e: &'a Expr) {
        if let Expr::Call(c) = e {
            if let Expr::Attribute(at) = &*c.func {
                if at.attr.id.as_str() == "parse_args" {
                    if let Some(pi) = self.parser_of(&at.value) {
                        let inner = &self.src[c.range()];
                        self.edits.push((c.range(), format!("_rupy_args_{}({})", pi, inner)));
                        return;
                    }
                }
            }
        }
        visitor::walk_expr(self, e);
    }
}

/// The program's text with its argparse uses typed (`None`: none).
pub fn expand(src: &str) -> Result<Option<String>, (u32, String)> {
    if !src.contains("argparse") {
        return Ok(None);
    }
    let Ok(parsed) = ruff_python_parser::parse_module(src) else { return Ok(None) };
    let body = &parsed.syntax().body;
    let mut scan = Scan { src, modules: vec![], classes: vec![], parsers: vec![], edits: vec![], err: None };
    for s in body {
        match s {
            Stmt::Import(i) => {
                for a in &i.names {
                    if a.name.id.as_str() == "argparse" {
                        scan.modules.push(a.asname.as_ref().unwrap_or(&a.name).id.to_string());
                    }
                }
            }
            Stmt::ImportFrom(i) if i.module.as_ref().is_some_and(|m| m.id.as_str() == "argparse") => {
                for a in &i.names {
                    if a.name.id.as_str() == "ArgumentParser" {
                        scan.classes.push(a.asname.as_ref().unwrap_or(&a.name).id.to_string());
                    }
                }
            }
            _ => {}
        }
    }
    if scan.modules.is_empty() && scan.classes.is_empty() {
        return Ok(None);
    }
    for s in body {
        scan.visit_stmt(s);
    }
    let lines = ruff_source_file::LineIndex::from_source_text(src);
    if let Some((r, m)) = scan.err {
        return Err((lines.line_index(r.start()).get() as u32, m));
    }
    if scan.parsers.is_empty() {
        return Ok(None);
    }
    let mut out = src.to_string();
    let mut edits = scan.edits;
    edits.sort_by_key(|(r, _)| std::cmp::Reverse(r.start()));
    for (r, new) in edits {
        out.replace_range(r.start().to_usize()..r.end().to_usize(), &new);
    }
    out.push_str("\n\nimport argparse as _rupy_argparse\nfrom dataclasses import dataclass\n");
    for (i, p) in scan.parsers.iter().enumerate() {
        out += &generated(i, p);
    }
    Ok(Some(out))
}

/// The dataclass of parser i's arguments, and the function that makes it.
fn generated(i: usize, p: &Parser) -> String {
    let mut fields = String::new();
    let mut body = String::new();
    let mut names = vec![];
    let mut reprs = vec![];
    for a in &p.args {
        let d = &a.dest;
        let v = format!("a_{}", d);
        let conv = |x: &str| if a.conv == "str" { x.to_string() } else { format!("{}({})", a.conv, x) };
        let list = !a.nargs.is_empty() && a.nargs != "?" || a.action == "append";
        let base = if list { format!("list[{}]", a.conv) } else { a.conv.clone() };
        let given = a.default.as_ref().filter(|x| x.trim() != "None").cloned();
        // (type, value when absent, value when given)
        let (ty, absent, got) = match a.action.as_str() {
            "store_true" => ("bool".to_string(), given.unwrap_or("False".into()), "True".to_string()),
            "store_false" => ("bool".to_string(), given.unwrap_or("True".into()), "False".to_string()),
            "count" => match given {
                Some(g) => ("int".to_string(), g.clone(), format!("{} + r.count({:?})", g, d)),
                None => ("int | None".to_string(), "None".into(), format!("r.count({:?})", d)),
            },
            _ => {
                let got = if list { format!("[{} for x in r.all({:?})]", conv("x"), d) } else { conv(&format!("r.one({:?})", d)) };
                let got = match (&given, a.action.as_str()) {
                    (Some(g), "append") => format!("{} + {}", g, got),
                    _ => got,
                };
                // a positional `*` gives []; a required one is always there
                match given {
                    Some(g) => (base, g, got),
                    None if a.positional && a.nargs == "*" => (base, "[]".into(), got),
                    None if a.required || a.positional && a.nargs != "?" => (base.clone(), String::new(), got),
                    None => (format!("{} | None", base), "None".into(), got),
                }
            }
        };
        fields += &format!("    {}: {}\n", d, ty);
        if absent.is_empty() {
            body += &format!("    {}: {} = {}\n", v, ty, got);
        } else {
            body += &format!("    {}: {} = {}\n    if r.has({:?}):\n        {} = {}\n", v, ty, absent, d, v, got);
        }
        names.push(v);
        reprs.push(format!("\"{}=\" + repr(self.{})", d, d));
    }
    let repr = if reprs.is_empty() { "\"Namespace()\"".to_string() } else { format!("\"Namespace(\" + {} + \")\"", reprs.join(" + \", \" + ")) };
    let fields = if fields.is_empty() { "    pass\n".to_string() } else { fields };
    format!(
        "\n\n@dataclass\nclass _RupyArgs{i}:\n{fields}\n    def __repr__(self) -> str:\n        return {repr}\n\n\ndef _rupy_args_{i}(r: _rupy_argparse.Parsed) -> _RupyArgs{i}:\n{body}    return _RupyArgs{i}({args})\n",
        args = names.join(", ")
    )
}
