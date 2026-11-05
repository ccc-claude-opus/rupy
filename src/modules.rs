//! Programs of several files: the local modules a program imports (`import m`,
//! `from m import x`, with `m.py` next to it) are appended to its source, so
//! the main file keeps its line numbers; errors are mapped back to the file.

use std::path::{Path, PathBuf};

use ruff_python_ast::{Expr as AExpr, Stmt as AStmt};
use ruff_source_file::LineIndex;
use ruff_text_size::{Ranged, TextRange};

use crate::diag::Error;

/// The combined source and where each file starts.
pub struct Combined {
    pub src: String,
    /// (first line in `src`, file, its text)
    pub parts: Vec<(u32, PathBuf, String)>,
    /// names of the local modules
    pub modules: Vec<String>,
}

/// An error in file `.0` (whose text is `.1`).
pub type FileError = (PathBuf, String, Error);

impl Combined {
    /// The file, its text and the line within it of a line of `src`.
    pub fn locate(&self, line: u32) -> (PathBuf, String, u32) {
        let mut best = &self.parts[0];
        for p in &self.parts {
            if p.0 <= line {
                best = p;
            }
        }
        (best.1.clone(), best.2.clone(), line - best.0 + 1)
    }
}

/// Queue the files of package `name` (once), and note the new names of its top-level names.
fn load_package(
    name: &str,
    packages: &mut Vec<(String, std::collections::HashMap<String, String>)>,
    queue: &mut Vec<(PathBuf, String, bool, Option<String>)>,
) -> Result<(), String> {
    if packages.iter().any(|(n, _)| n == name) {
        return Ok(());
    }
    let files = crate::pkgsrc::package_files(name).ok_or_else(|| format!("no package `{}`", name))?;
    let mut map = std::collections::HashMap::new();
    for (_, text) in &files {
        if let Ok(m) = ruff_python_parser::parse_module(text) {
            for n in crate::pkgsrc::top_names(&m.into_syntax().body) {
                map.insert(n.clone(), crate::pkgsrc::mangle(name, &n));
            }
        }
    }
    packages.push((name.to_string(), map));
    for (f, text) in files {
        queue.push((f, text, false, Some(name.to_string())));
    }
    Ok(())
}

/// Spaces in place of a statement (newlines kept).
fn blank(text: &mut String, r: TextRange) {
    let (a, b) = (r.start().to_usize(), r.end().to_usize());
    let rep: String = text[a..b].chars().map(|c| if c == '\n' { '\n' } else { ' ' }).collect();
    text.replace_range(a..b, &rep);
}

fn is_main_guard(s: &AStmt) -> bool {
    let AStmt::If(i) = s else { return false };
    let AExpr::Compare(c) = &*i.test else { return false };
    matches!(c.operands.first(), Some(AExpr::Name(n)) if n.id.as_str() == "__name__")
}

fn err_at(path: &Path, text: &str, r: TextRange, msg: String) -> FileError {
    let line = LineIndex::from_source_text(text).line_index(r.start()).get() as u32;
    (path.to_path_buf(), text.to_string(), Error::new(line, msg))
}

/// Reads `path` and the local modules it imports.
pub fn combine(path: &Path) -> Result<Combined, FileError> {
    let main = std::fs::read_to_string(path).map_err(|e| (path.to_path_buf(), String::new(), Error::new(0, e.to_string())))?;
    combine_text(path, main)
}

/// [`combine`] of a program whose text is given (in a browser: no files but
/// the packages built into rupy).
pub fn combine_text(path: &Path, main: String) -> Result<Combined, FileError> {
    let dir = path.parent().map(Path::to_path_buf).unwrap_or_default();
    let read = |p: &Path| std::fs::read_to_string(p).map_err(|e| (p.to_path_buf(), String::new(), Error::new(0, e.to_string())));
    let mut out = Combined { src: String::new(), parts: vec![], modules: vec![] };
    let main_text = main.clone();
    // (file, text, is the main file, the package it belongs to)
    let mut queue: Vec<(PathBuf, String, bool, Option<String>)> = vec![(path.to_path_buf(), main, true, None)];
    let mut texts: Vec<(PathBuf, String)> = vec![];
    // packages written in rupy: name → the new names of their top-level names
    let mut packages: Vec<(String, std::collections::HashMap<String, String>)> = vec![];
    while let Some((p, text, is_main, in_pkg)) = queue.pop() {
        let parsed = match ruff_python_parser::parse_module(&text) {
            Ok(m) => m.into_syntax(),
            // syntax errors are reported by the translator itself
            Err(_) => {
                texts.push((p, text));
                continue;
            }
        };
        let mut t = text.clone();
        // this file's `import PKG as A` (A → PKG) and `from PKG import x` (x → PKG__x)
        let mut aliases: std::collections::HashMap<String, String> = Default::default();
        let mut froms: std::collections::HashMap<String, String> = Default::default();
        for s in parsed.body.iter() {
            // a package written in rupy
            let pkg_of = |m: &str| {
                let root = m.split('.').next().unwrap_or(m);
                (crate::pkgsrc::is_package(root) && !dir.join(format!("{}.py", root)).exists()).then(|| root.to_string())
            };
            match s {
                AStmt::Import(i) if i.names.iter().any(|a| pkg_of(a.name.id.as_str()).is_some()) => {
                    if i.names.iter().any(|a| pkg_of(a.name.id.as_str()).is_none()) {
                        return Err(err_at(&p, &text, s.range(), "import packages on their own line".into()));
                    }
                    for a in &i.names {
                        let pkg = pkg_of(a.name.id.as_str()).unwrap();
                        if in_pkg.as_deref() != Some(pkg.as_str()) {
                            aliases.insert(a.asname.as_ref().map(|n| n.id.to_string()).unwrap_or_else(|| pkg.clone()), pkg.clone());
                            load_package(&pkg, &mut packages, &mut queue).map_err(|e| err_at(&p, &text, s.range(), e))?;
                        }
                    }
                    blank(&mut t, s.range());
                    continue;
                }
                AStmt::ImportFrom(i) if i.level == 0 && i.module.as_ref().is_some_and(|m| pkg_of(m.id.as_str()).is_some()) => {
                    let pkg = pkg_of(i.module.as_ref().unwrap().id.as_str()).unwrap();
                    // inside the package its names are already the package's
                    if in_pkg.as_deref() != Some(pkg.as_str()) {
                        load_package(&pkg, &mut packages, &mut queue).map_err(|e| err_at(&p, &text, s.range(), e))?;
                        for a in &i.names {
                            if a.name.id.as_str() == "*" {
                                return Err(err_at(&p, &text, s.range(), "`from PACKAGE import *` is not supported".into()));
                            }
                            let new = crate::pkgsrc::export(&pkg, &a.name.id);
                            froms.insert(a.asname.as_ref().unwrap_or(&a.name).id.to_string(), new);
                        }
                    }
                    blank(&mut t, s.range());
                    continue;
                }
                _ => {}
            }
            let local = |m: &str| {
                let f = dir.join(format!("{}.py", m));
                f.exists() && f != path
            };
            match s {
                AStmt::Import(i) => {
                    let names: Vec<&str> = i.names.iter().map(|a| a.name.id.as_str()).collect();
                    if names.iter().any(|n| local(n)) {
                        if names.iter().any(|n| !local(n)) || i.names.iter().any(|a| a.asname.is_some()) {
                            return Err(err_at(&p, &text, s.range(), "import local modules on their own line, without `as`".into()));
                        }
                        for n in names {
                            if !out.modules.iter().any(|m| m == n) {
                                out.modules.push(n.to_string());
                                let f = dir.join(format!("{}.py", n));
                                queue.push((f.clone(), read(&f)?, false, None));
                            }
                        }
                        blank(&mut t, s.range());
                    }
                }
                AStmt::ImportFrom(i) if i.level == 0 && i.module.as_ref().is_some_and(|m| local(m.id.as_str())) => {
                    let n = i.module.as_ref().unwrap().id.to_string();
                    if i.names.iter().any(|a| a.asname.is_some() || a.name.id.as_str() == "*") {
                        return Err(err_at(&p, &text, s.range(), "`from module import x as y` / `*` is not supported for local modules".into()));
                    }
                    if !out.modules.contains(&n) {
                        out.modules.push(n.clone());
                        let f = dir.join(format!("{}.py", n));
                        queue.push((f.clone(), read(&f)?, false, None));
                    }
                    blank(&mut t, s.range());
                }
                _ if is_main => {}
                // an imported module only defines things
                AStmt::FunctionDef(_) | AStmt::ClassDef(_) | AStmt::ImportFrom(_) | AStmt::Pass(_) => {}
                AStmt::Assign(_) | AStmt::AnnAssign(_) => {}
                AStmt::Expr(e) if matches!(&*e.value, AExpr::StringLiteral(_)) => {}
                _ if is_main_guard(s) => blank(&mut t, s.range()),
                _ => {
                    return Err(err_at(&p, &text, s.range(), "an imported module may only define functions, classes and constants".into()))
                }
            }
        }
        // the package's names renamed in its files; the program's references to them
        let mut map = froms;
        if let Some(pkg) = &in_pkg {
            map.extend(packages.iter().find(|(n, _)| n == pkg).map(|(_, m)| m.clone()).unwrap_or_default());
        }
        if !map.is_empty() || !aliases.is_empty() {
            t = crate::pkgsrc::rewrite(&t, &parsed.body, &map, &aliases);
        }
        texts.push((p, t));
    }
    // the main file first, then the modules in the order they were found
    let main_idx = texts.iter().position(|(p, _)| p == path).unwrap();
    let main = texts.remove(main_idx);
    let mut line = 1u32;
    for (p, t) in std::iter::once(main).chain(texts) {
        let original = if p == path { main_text.clone() } else { std::fs::read_to_string(&p).unwrap_or_default() };
        out.parts.push((line, p, original));
        out.src += &t;
        if !t.ends_with('\n') {
            out.src.push('\n');
        }
        line = out.src.lines().count() as u32 + 1;
    }
    Ok(out)
}
