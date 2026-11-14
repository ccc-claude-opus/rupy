//! `operator`: its functions become the expressions they stand for before
//! lowering. `operator.add(a, b)` is `(a + b)`, `operator.add` as a value is
//! `(lambda x, y: x + y)`, `itemgetter(1)` is `(lambda x: x[1])`,
//! `attrgetter("a.b")` is `(lambda x: x.a.b)` and `methodcaller("m", 2)` is
//! `(lambda x: x.m(2))`. The new code is parsed and moved to the place of the
//! code it replaces.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::transformer::{self, Transformer};
use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::diag::{Error, Res};

/// Binary operators: (function, Python operator); `contains(a, b)` is `b in a`.
const BINARY: &[(&str, &str)] = &[
    ("add", "+"), ("sub", "-"), ("mul", "*"), ("truediv", "/"), ("floordiv", "//"), ("mod", "%"), ("pow", "**"),
    ("lshift", "<<"), ("rshift", ">>"), ("and_", "&"), ("or_", "|"), ("xor", "^"), ("matmul", "@"), ("concat", "+"),
    ("eq", "=="), ("ne", "!="), ("lt", "<"), ("le", "<="), ("gt", ">"), ("ge", ">="), ("is_", "is"), ("is_not", "is not"),
];

/// Unary operators: (function, the expression with `A`).
const UNARY: &[(&str, &str)] = &[("neg", "-A"), ("pos", "+A"), ("not_", "not A"), ("truth", "bool(A)"), ("abs", "abs(A)"), ("invert", "~A"), ("inv", "~A")];

struct Rewriter<'s> {
    src: &'s str,
    /// `import operator [as m]`: the module's names
    modules: &'s HashSet<String>,
    /// `from operator import f [as g]`: g → f
    names: &'s HashMap<String, String>,
    lines: &'s ruff_source_file::LineIndex,
    err: RefCell<Option<Error>>,
}

impl Rewriter<'_> {
    /// The operator function `e` names, if any.
    fn function(&self, e: &Expr) -> Option<String> {
        match e {
            Expr::Attribute(a) => match &*a.value {
                Expr::Name(m) if self.modules.contains(m.id.as_str()) => Some(a.attr.id.to_string()),
                _ => None,
            },
            Expr::Name(n) => self.names.get(n.id.as_str()).cloned(),
            _ => None,
        }
    }

    fn fail(&self, at: TextRange, msg: String) {
        let line = self.lines.line_index(at.start()).get() as u32;
        self.err.borrow_mut().get_or_insert(Error::new(line, msg));
    }

    /// The code for `f(args)` (`args`: source texts), or for `f` alone.
    fn code(&self, f: &str, args: Option<&[String]>, at: TextRange) -> Option<String> {
        let one = |s: &Self| -> Option<String> {
            match args {
                Some([a]) => Some(a.clone()),
                _ => {
                    s.fail(at, format!("operator.{}() takes one argument here", f));
                    None
                }
            }
        };
        if let Some((_, op)) = BINARY.iter().find(|(n, _)| *n == f) {
            return Some(match args {
                Some([a, b]) => format!("(({}) {} ({}))", a, op, b),
                None => format!("(lambda __op_a, __op_b: __op_a {} __op_b)", op),
                _ => {
                    self.fail(at, format!("operator.{}() takes two arguments", f));
                    return None;
                }
            });
        }
        if f == "contains" || f == "getitem" {
            let (x, y) = if f == "contains" { ("{1} in {0}", "__op_b in __op_a") } else { ("{0}[{1}]", "__op_a[__op_b]") };
            return Some(match args {
                Some([a, b]) => format!("({})", x.replace("{0}", &format!("({})", a)).replace("{1}", &format!("({})", b))),
                None => format!("(lambda __op_a, __op_b: {})", y),
                _ => {
                    self.fail(at, format!("operator.{}() takes two arguments", f));
                    return None;
                }
            });
        }
        if let Some((_, form)) = UNARY.iter().find(|(n, _)| *n == f) {
            return Some(match args {
                Some(_) => format!("({})", form.replace('A', &format!("({})", one(self)?))),
                None => format!("(lambda __op_a: {})", form.replace('A', "__op_a")),
            });
        }
        let Some(args) = args else {
            self.fail(at, format!("operator.{} is supported when it is called", f));
            return None;
        };
        let body = match f {
            "itemgetter" => args.iter().map(|a| format!("__op_x[{}]", a)).collect::<Vec<_>>(),
            "attrgetter" => {
                let mut v = vec![];
                for a in args {
                    let name = a.trim().trim_matches(|c| c == '"' || c == '\'');
                    if name.len() + 2 != a.trim().len() || name.is_empty() || !name.split('.').all(|p| !p.is_empty() && p.chars().all(|c| c.is_alphanumeric() || c == '_')) {
                        self.fail(at, "operator.attrgetter() needs string literals of attribute names".into());
                        return None;
                    }
                    v.push(format!("__op_x.{}", name));
                }
                v
            }
            "methodcaller" => {
                let Some((m, rest)) = args.split_first() else {
                    self.fail(at, "operator.methodcaller() needs a method name".into());
                    return None;
                };
                let name = m.trim().trim_matches(|c| c == '"' || c == '\'');
                if name.len() + 2 != m.trim().len() || !name.chars().all(|c| c.is_alphanumeric() || c == '_') {
                    self.fail(at, "operator.methodcaller() needs a string literal method name".into());
                    return None;
                }
                vec![format!("__op_x.{}({})", name, rest.join(", "))]
            }
            _ => {
                self.fail(at, format!("operator.{} is not supported", f));
                return None;
            }
        };
        if body.is_empty() {
            self.fail(at, format!("operator.{}() needs arguments", f));
            return None;
        }
        Some(if body.len() == 1 { format!("(lambda __op_x: {})", body[0]) } else { format!("(lambda __op_x: ({}))", body.join(", ")) })
    }

    /// Replace `e` by `code`, parsed, rewritten in turn and moved to `e`'s place.
    fn replace(&self, e: &mut Expr, code: String) {
        let at = e.range();
        let parsed = match ruff_python_parser::parse_expression(&code) {
            Ok(p) => p.into_expr(),
            Err(_) => {
                self.fail(at, "this use of operator is not supported".into());
                return;
            }
        };
        let mut new = parsed;
        let inner = Rewriter { src: &code, modules: self.modules, names: self.names, lines: self.lines, err: RefCell::new(None) };
        inner.visit_expr(&mut new);
        if let Some(x) = inner.err.into_inner() {
            self.err.borrow_mut().get_or_insert(x);
        }
        ruff_python_ast::relocate::relocate_expr(&mut new, at);
        *e = new;
    }
}

impl Transformer for Rewriter<'_> {
    fn visit_expr(&self, e: &mut Expr) {
        if let Expr::Call(c) = e {
            if let Some(f) = self.function(&c.func) {
                if !c.arguments.keywords.is_empty() {
                    self.fail(c.range(), format!("operator.{}() takes no keyword arguments", f));
                    return;
                }
                let args: Vec<String> = c.arguments.args.iter().map(|a| self.src[a.range()].to_string()).collect();
                if let Some(code) = self.code(&f, Some(&args), c.range()) {
                    self.replace(e, code);
                }
                return;
            }
        }
        if let Some(f) = self.function(e) {
            if let Some(code) = self.code(&f, None, e.range()) {
                self.replace(e, code);
            }
            return;
        }
        transformer::walk_expr(self, e);
    }
}

/// Rewrite the uses of `operator` in `body` and drop its imports.
pub(super) fn desugar(module: &mut ruff_python_ast::ModModule, src: &str, lines: &ruff_source_file::LineIndex) -> Res<()> {
    let body = &mut module.body;
    let mut modules = HashSet::new();
    let mut names = HashMap::new();
    let mut found = false;
    body.retain(|s| match s {
        Stmt::Import(i) if i.names.iter().all(|a| a.name.id.as_str() == "operator") => {
            for a in &i.names {
                modules.insert(a.asname.as_ref().unwrap_or(&a.name).id.to_string());
            }
            found = true;
            false
        }
        Stmt::ImportFrom(i) if i.level == 0 && i.module.as_ref().is_some_and(|m| m.id.as_str() == "operator") => {
            for a in &i.names {
                names.insert(a.asname.as_ref().unwrap_or(&a.name).id.to_string(), a.name.id.to_string());
            }
            found = true;
            false
        }
        _ => true,
    });
    if !found {
        return Ok(());
    }
    let r = Rewriter { src, modules: &modules, names: &names, lines, err: RefCell::new(None) };
    for s in body.iter_mut() {
        r.visit_stmt(s);
    }
    match r.err.into_inner() {
        Some(e) => Err(e),
        None => Ok(()),
    }
}
