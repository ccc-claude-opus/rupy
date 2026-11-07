//! Packages written in rupy (`.py` sources, like `rstatistics`): their files are
//! appended to the program like local modules, with every top-level name
//! renamed `PKG__name` so they cannot clash with the program's names. The
//! program's `import PKG as A` / `A.name` and `from PKG import name` are
//! rewritten to those names. Renaming follows Python's scopes: a function's
//! parameters and locals keep their names.

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{self as ast, Expr, ExprContext, Stmt};
use ruff_text_size::{Ranged, TextRange};

/// Packages written in rupy that are built into rupy (a browser has no files):
/// (package, file name, source).
const BUILTIN: &[(&str, &str, &str)] = &[
    ("rstatistics", "__init__.py", include_str!("../rstatistics/rstatistics/__init__.py")),
    ("rstatistics", "distributions.py", include_str!("../rstatistics/rstatistics/distributions.py")),
    ("rstatistics", "describe.py", include_str!("../rstatistics/rstatistics/describe.py")),
    ("rstatistics", "graphics.py", include_str!("../rstatistics/rstatistics/graphics.py")),
    ("rstatistics", "htest.py", include_str!("../rstatistics/rstatistics/htest.py")),
    ("rstatistics", "lm.py", include_str!("../rstatistics/rstatistics/lm.py")),
    ("rstatistics", "rformat.py", include_str!("../rstatistics/rstatistics/rformat.py")),
    ("rstatistics", "rng.py", include_str!("../rstatistics/rstatistics/rng.py")),
    ("rstatistics", "special.py", include_str!("../rstatistics/rstatistics/special.py")),
];

/// The files of package `name`: `DIR/name/*.py` (with an `__init__.py`) in the
/// package directories, else a built-in copy. (file, text) pairs, sorted.
pub fn package_files(name: &str) -> Option<Vec<(PathBuf, String)>> {
    let mut dirs = crate::front::package_dirs();
    dirs.push(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(name));
    for d in dirs {
        let pkg = d.join(name);
        if pkg.join("__init__.py").is_file() {
            let mut files: Vec<PathBuf> = std::fs::read_dir(&pkg).ok()?.flatten().map(|e| e.path()).filter(|p| p.extension().is_some_and(|e| e == "py")).collect();
            files.sort();
            return files.into_iter().map(|f| std::fs::read_to_string(&f).ok().map(|t| (f, t))).collect();
        }
    }
    let files: Vec<(PathBuf, String)> =
        BUILTIN.iter().filter(|(p, _, _)| *p == name).map(|(p, f, t)| (PathBuf::from(format!("{}/{}", p, f)), t.to_string())).collect();
    (!files.is_empty()).then_some(files)
}

/// Whether there is a package `name` written in rupy.
pub fn is_package(name: &str) -> bool {
    BUILTIN.iter().any(|(p, _, _)| *p == name) || package_files(name).is_some()
}

/// The new name of `name` of package `pkg`.
pub fn mangle(pkg: &str, name: &str) -> String {
    format!("{}__{}", pkg, name)
}

/// The new name of `name` as the program sees package `pkg`: a name its
/// `__init__.py` re-exports under another (`from pkg.m import a as name`) is
/// `a`'s. (Inside the package `name` keeps its meaning, a builtin say.)
pub fn export(pkg: &str, name: &str) -> String {
    thread_local! {
        static RENAMED: std::cell::RefCell<HashMap<String, HashMap<String, String>>> = Default::default();
    }
    let real = RENAMED.with(|r| {
        let mut r = r.borrow_mut();
        let m = r.entry(pkg.to_string()).or_insert_with(|| {
            let mut m = HashMap::new();
            let init = package_files(pkg).unwrap_or_default().into_iter().find(|(f, _)| f.ends_with("__init__.py"));
            if let Some(Ok(parsed)) = init.map(|(_, t)| ruff_python_parser::parse_module(&t)) {
                for s in &parsed.syntax().body {
                    if let Stmt::ImportFrom(i) = s {
                        for a in &i.names {
                            if let Some(asname) = &a.asname {
                                m.insert(asname.id.to_string(), a.name.id.to_string());
                            }
                        }
                    }
                }
            }
            m
        });
        m.get(name).cloned()
    });
    mangle(pkg, real.as_deref().unwrap_or(name))
}

/// The top-level names a module defines.
pub fn top_names(body: &[Stmt]) -> Vec<String> {
    let mut out = vec![];
    for s in body {
        match s {
            Stmt::FunctionDef(f) => out.push(f.name.id.to_string()),
            Stmt::ClassDef(c) => out.push(c.name.id.to_string()),
            Stmt::Assign(a) => {
                for t in &a.targets {
                    if let Expr::Name(n) = t {
                        out.push(n.id.to_string());
                    }
                }
            }
            Stmt::AnnAssign(a) => {
                if let Expr::Name(n) = &*a.target {
                    out.push(n.id.to_string());
                }
            }
            _ => {}
        }
    }
    out
}

/// Rewrite `text` (parsed as `body`): the names in `map` (where they are not
/// shadowed) and the attributes `A.x` of the aliases (`A` → package prefix).
pub fn rewrite(text: &str, body: &[Stmt], map: &HashMap<String, String>, aliases: &HashMap<String, String>) -> String {
    let mut r = Renamer { map, aliases, scopes: vec![], edits: vec![], in_annotation: false };
    r.visit_body(body);
    let mut edits = r.edits;
    edits.sort_by_key(|(range, _)| std::cmp::Reverse(range.start()));
    let mut out = text.to_string();
    let mut last = usize::MAX;
    for (range, new) in edits {
        let (a, b) = (range.start().to_usize(), range.end().to_usize());
        // nested edits (an alias attribute inside one already rewritten) are skipped
        if b > last {
            continue;
        }
        out.replace_range(a..b, &new);
        last = a;
    }
    out
}

struct Renamer<'m> {
    map: &'m HashMap<String, String>,
    /// alias → package prefix
    aliases: &'m HashMap<String, String>,
    /// local names of the enclosing functions, classes and comprehensions
    scopes: Vec<HashSet<String>>,
    edits: Vec<(TextRange, String)>,
    in_annotation: bool,
}

impl Renamer<'_> {
    fn local(&self, name: &str) -> bool {
        self.scopes.iter().any(|s| s.contains(name))
    }
    fn rename(&mut self, name: &str, range: TextRange) {
        if !self.local(name) {
            if let Some(new) = self.map.get(name) {
                self.edits.push((range, new.clone()));
            }
        }
    }
}

/// The names a function (or class) body binds, without entering nested scopes.
#[derive(Default)]
struct Binds {
    names: HashSet<String>,
    globals: HashSet<String>,
}

impl<'a> Visitor<'a> for Binds {
    fn visit_stmt(&mut self, s: &'a Stmt) {
        match s {
            Stmt::FunctionDef(f) => {
                self.names.insert(f.name.id.to_string());
            }
            Stmt::ClassDef(c) => {
                self.names.insert(c.name.id.to_string());
            }
            Stmt::Global(g) => self.globals.extend(g.names.iter().map(|n| n.id.to_string())),
            Stmt::Import(i) => {
                for a in &i.names {
                    let n = a.asname.as_ref().unwrap_or(&a.name).id.to_string();
                    self.names.insert(n.split('.').next().unwrap_or("").to_string());
                }
            }
            Stmt::ImportFrom(i) => {
                for a in &i.names {
                    self.names.insert(a.asname.as_ref().unwrap_or(&a.name).id.to_string());
                }
            }
            _ => visitor::walk_stmt(self, s),
        }
    }
    fn visit_expr(&mut self, e: &'a Expr) {
        match e {
            Expr::Name(n) if n.ctx == ExprContext::Store => {
                self.names.insert(n.id.to_string());
            }
            // their own scopes
            Expr::Lambda(_) | Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_) => {}
            _ => visitor::walk_expr(self, e),
        }
    }
    fn visit_except_handler(&mut self, h: &'a ast::ExceptHandler) {
        let ast::ExceptHandler::ExceptHandler(h) = h;
        if let Some(n) = &h.name {
            self.names.insert(n.id.to_string());
        }
        self.visit_body(&h.body);
    }
}

fn binds(body: &[Stmt], params: Option<&ast::Parameters>) -> HashSet<String> {
    let mut b = Binds::default();
    b.visit_body(body);
    if let Some(ps) = params {
        for p in ps.iter() {
            b.names.insert(p.name().id.to_string());
        }
    }
    b.names.retain(|n| !b.globals.contains(n));
    b.names
}

impl<'a> Visitor<'a> for Renamer<'_> {
    fn visit_stmt(&mut self, s: &'a Stmt) {
        match s {
            Stmt::FunctionDef(f) => {
                if self.scopes.is_empty() {
                    self.rename(&f.name.id, f.name.range);
                }
                // decorators, defaults and annotations belong to the enclosing scope
                for d in &f.decorator_list {
                    self.visit_decorator(d);
                }
                for p in f.parameters.iter() {
                    if let Some(a) = p.annotation() {
                        self.visit_annotation(a);
                    }
                    if let Some(d) = p.default() {
                        self.visit_expr(d);
                    }
                }
                if let Some(r) = &f.returns {
                    self.visit_annotation(r);
                }
                self.scopes.push(binds(&f.body, Some(&f.parameters)));
                self.visit_body(&f.body);
                self.scopes.pop();
            }
            Stmt::ClassDef(c) => {
                if self.scopes.is_empty() {
                    self.rename(&c.name.id, c.name.range);
                }
                for d in &c.decorator_list {
                    self.visit_decorator(d);
                }
                if let Some(args) = &c.arguments {
                    self.visit_arguments(args);
                }
                // the class body's names are attributes, not the module's
                self.scopes.push(binds(&c.body, None));
                self.visit_body(&c.body);
                self.scopes.pop();
            }
            _ => visitor::walk_stmt(self, s),
        }
    }

    fn visit_annotation(&mut self, e: &'a Expr) {
        let saved = std::mem::replace(&mut self.in_annotation, true);
        self.visit_expr(e);
        self.in_annotation = saved;
    }

    fn visit_expr(&mut self, e: &'a Expr) {
        match e {
            Expr::Name(n) => self.rename(&n.id, n.range),
            // `A.x` of a package imported as `A`
            Expr::Attribute(a) if matches!(&*a.value, Expr::Name(m) if self.aliases.contains_key(m.id.as_str()) && !self.local(m.id.as_str())) => {
                let Expr::Name(m) = &*a.value else { unreachable!() };
                self.edits.push((a.range, export(&self.aliases[m.id.as_str()], &a.attr.id)));
            }
            // a forward reference in an annotation: `"HTest"`
            Expr::StringLiteral(s) if self.in_annotation => {
                let v = s.value.to_str();
                if let Some(new) = self.map.get(v).filter(|_| !self.local(v)) {
                    self.edits.push((s.range, format!("{:?}", new)));
                }
            }
            Expr::Lambda(l) => {
                let mut names = HashSet::new();
                if let Some(ps) = &l.parameters {
                    for p in ps.iter() {
                        names.insert(p.name().id.to_string());
                    }
                }
                self.scopes.push(names);
                self.visit_expr(&l.body);
                self.scopes.pop();
            }
            Expr::ListComp(_) | Expr::SetComp(_) | Expr::DictComp(_) | Expr::Generator(_) => {
                let gens: &[ast::Comprehension] = match e {
                    Expr::ListComp(c) => &c.generators,
                    Expr::SetComp(c) => &c.generators,
                    Expr::DictComp(c) => &c.generators,
                    Expr::Generator(c) => &c.generators,
                    _ => unreachable!(),
                };
                // the first iterable is evaluated outside; the targets are local
                let mut names = HashSet::new();
                for g in gens {
                    let mut b = Binds::default();
                    b.visit_expr(&g.target);
                    names.extend(b.names);
                }
                if let Some(g) = gens.first() {
                    self.visit_expr(&g.iter);
                }
                self.scopes.push(names);
                for (i, g) in gens.iter().enumerate() {
                    if i > 0 {
                        self.visit_expr(&g.iter);
                    }
                    for c in &g.ifs {
                        self.visit_expr(c);
                    }
                }
                match e {
                    Expr::ListComp(c) => self.visit_expr(&c.elt),
                    Expr::SetComp(c) => self.visit_expr(&c.elt),
                    Expr::Generator(c) => self.visit_expr(&c.elt),
                    Expr::DictComp(c) => {
                        if let Some(k) = &c.key {
                            self.visit_expr(k);
                        }
                        self.visit_expr(&c.value);
                    }
                    _ => {}
                }
                self.scopes.pop();
            }
            _ => visitor::walk_expr(self, e),
        }
    }
}
