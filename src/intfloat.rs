//! Ints in float places. `x: float = 3` holds the int 3 in CPython (it prints
//! `3`), while rupy's float prints `3.0`. Such a value stays an int in CPython
//! through `+`, `-`, `*`, `//`, `%`, `abs`, `max`, ... with other ints, until a
//! float or `/` meets it. This pass follows these "maybe int" floats (through
//! variables, parameters, returns, fields and containers, to a fixpoint) and
//! rejects a program that shows one as text: `print`, `str`, `repr`, an
//! f-string without a float format, `json.dumps`. A function is analyzed once
//! per set of parameters that receive such values (`scale(3, 2.5)` returns a
//! float, `scale(3, 2)` a maybe-int).

use std::collections::{HashMap, HashSet};

use crate::diag::{err, Res};
use crate::ir::*;

fn has_float(t: &Ty) -> bool {
    match t {
        Ty::Float => true,
        Ty::List(e) | Ty::Set(e) | Ty::Optional(e) | Ty::Deque(e) | Ty::Gen(e) => has_float(e),
        Ty::Dict(k, v, _) => has_float(k) || has_float(v),
        Ty::Tuple(ts) => ts.iter().any(has_float),
        _ => false,
    }
}

/// A function analyzed for the parameters (bits) that receive maybe-ints.
type Ctx = (FuncId, u64);

#[derive(Default)]
struct Taint {
    /// the maybe-int variables of each context
    vars: HashMap<Ctx, HashSet<VarId>>,
    rets: HashSet<Ctx>,
    fields: HashSet<(ClassId, String)>,
}

struct Pass<'a> {
    p: &'a Program,
    t: Taint,
    changed: bool,
    /// the context being analyzed
    cur: Ctx,
}

fn params_of(p: &Program, g: FuncId) -> Vec<VarId> {
    let func = &p.funcs[g];
    func.params.iter().map(|q| q.var).filter(|v| Some(*v) != func.self_var).collect()
}

impl Pass<'_> {
    fn mark_var(&mut self, _f: FuncId, v: VarId) {
        if self.t.vars.entry(self.cur).or_default().insert(v) {
            self.changed = true;
        }
    }

    /// The context of a call: `g` with the parameters its arguments taint.
    fn callee(&self, f: FuncId, g: FuncId, args: &[Expr]) -> Ctx {
        let mut mask = 0u64;
        for (i, a) in args.iter().enumerate().take(64) {
            if self.tainted(f, a) {
                mask |= 1 << i;
            }
        }
        (g, mask)
    }

    fn class_of(t: &Ty) -> Option<ClassId> {
        match t {
            Ty::Class(c) | Ty::Obj(c) => Some(*c),
            _ => None,
        }
    }

    /// May `e` (of a type with floats) hold ints where CPython would?
    fn tainted(&self, f: FuncId, e: &Expr) -> bool {
        use ExprKind as K;
        if !has_float(&e.ty) {
            return false;
        }
        let intlike = |s: &Self, x: &Expr| matches!(x.ty, Ty::Int | Ty::Bool) || s.tainted(f, x);
        match &e.kind {
            K::ToFloat(_) => true,
            K::Var(v) => self.t.vars.get(&self.cur).is_some_and(|s| s.contains(v)),
            K::Const(i) => self.const_tainted(*i),
            K::Call(g, args) | K::Method(_, g, args) => self.t.rets.contains(&self.callee(f, *g, args)),
            K::Field(o, name) => Self::class_of(&o.ty).is_some_and(|c| self.field(c, name)),
            K::Index(c, _) | K::Slice(c, ..) => self.tainted(f, c),
            K::TupleField(c, _) => self.tainted(f, c),
            K::List(xs) | K::Tuple(xs) | K::Set(xs) => xs.iter().any(|x| self.tainted(f, x)),
            K::Dict(kv) => kv.iter().any(|(k, v)| self.tainted(f, k) || self.tainted(f, v)),
            K::Comp(c) => self.tainted(f, &c.elt) || c.val.as_ref().is_some_and(|v| self.tainted(f, v)),
            K::IfExp(_, a, b) => self.tainted(f, a) || self.tainted(f, b),
            K::Bin(op, a, b) => match op {
                BinOp::Div => false,
                _ if matches!(e.ty, Ty::Float) => intlike(self, a) && intlike(self, b) && (self.tainted(f, a) || self.tainted(f, b)),
                // lists: `xs + ys`, `xs * 2`
                _ => self.tainted(f, a) || self.tainted(f, b),
            },
            K::Unary(_, a) | K::SomeOf(a) | K::Upcast(a) => self.tainted(f, a),
            K::Builtin(name, args) => {
                if *name == "float" || name.starts_with("math.") || name.starts_with("random.") || name.starts_with("time.") {
                    return false;
                }
                args.iter().any(|x| self.tainted(f, x))
            }
            K::Iter(it) => {
                let mut any = false;
                it.exprs(&mut |x| any |= self.tainted(f, x));
                any
            }
            _ => false,
        }
    }

    /// A module constant (`X: float = 3`): its literal decides.
    fn const_tainted(&self, i: usize) -> bool {
        fn lit(e: &Expr) -> bool {
            match &e.kind {
                ExprKind::ToFloat(_) => true,
                _ => {
                    let mut any = false;
                    e.children(&mut |c| any |= has_float(&c.ty) && lit(c));
                    any
                }
            }
        }
        lit(&self.p.consts[i].value)
    }

    fn field(&self, c: ClassId, name: &str) -> bool {
        // a field of a base class is the field of each subclass too
        self.t.fields.iter().any(|(k, n)| n == name && (*k == c || self.p.is_sub(c, *k) || self.p.is_sub(*k, c)))
    }

    fn target(&mut self, f: FuncId, t: &Target, tainted: bool) {
        if !tainted {
            return;
        }
        match t {
            Target::Var(v) => self.mark_var(f, *v),
            Target::Tuple(ts) => ts.iter().for_each(|x| self.target(f, x, true)),
            Target::Place(p) => self.place(f, p),
        }
    }

    /// A tainted value stored into `p` (`xs[i]`, `d[k]`, `o.f`): its container.
    fn place(&mut self, f: FuncId, p: &Expr) {
        match &p.kind {
            ExprKind::Var(v) => self.mark_var(f, *v),
            ExprKind::Index(c, _) | ExprKind::TupleField(c, _) => self.place(f, c),
            ExprKind::Field(o, name) => {
                if let Some(c) = Self::class_of(&o.ty) {
                    if self.t.fields.insert((c, name.clone())) {
                        self.changed = true;
                    }
                }
            }
            _ => {}
        }
    }

    fn iter(&mut self, f: FuncId, t: &Target, it: &Iter) {
        let mut any = false;
        it.exprs(&mut |x| any |= self.tainted(f, x));
        self.target(f, t, any);
    }

    fn expr(&mut self, f: FuncId, e: &Expr) {
        use ExprKind as K;
        match &e.kind {
            K::Call(g, args) | K::Method(_, g, args) => {
                let ctx = self.callee(f, *g, args);
                if let std::collections::hash_map::Entry::Vacant(v) = self.t.vars.entry(ctx) {
                    v.insert(HashSet::new());
                    self.changed = true;
                }
            }
            K::New(c, args) => {
                if let Some(init) = self.p.init_for(*c, args) {
                    let ctx = self.callee(f, init, args);
                    if let std::collections::hash_map::Entry::Vacant(v) = self.t.vars.entry(ctx) {
                        v.insert(HashSet::new());
                        self.changed = true;
                    }
                } else {
                    // a dataclass: arguments in field order
                    let fields: Vec<String> = self.p.classes[*c].fields.iter().map(|x| x.name.clone()).collect();
                    for (n, a) in fields.iter().zip(args.iter()) {
                        if self.tainted(f, a) && self.t.fields.insert((*c, n.clone())) {
                            self.changed = true;
                        }
                    }
                }
            }
            // `xs.append(3)` into a list[float]
            K::Builtin(name, args) if args.len() >= 2 && (name.starts_with("list.") || name.starts_with("dict.") || name.starts_with("set.") || name.starts_with("deque.") || name.starts_with("heapq.")) => {
                if args[1..].iter().any(|a| self.tainted(f, a)) {
                    self.place(f, &args[0]);
                }
            }
            K::Builtin("yield", args) => {
                if args.iter().any(|a| self.tainted(f, a)) && self.t.rets.insert(self.cur) {
                    self.changed = true;
                }
            }
            K::Comp(c) => {
                for g in &c.gens {
                    self.iter(f, &g.target, &g.iter);
                }
            }
            _ => {}
        }
        e.children(&mut |c| self.expr(f, c));
    }

    fn stmts(&mut self, f: FuncId, body: &[Stmt]) {
        for s in body {
            match &s.kind {
                StmtKind::Assign(t, e) => {
                    let tt = self.tainted(f, e);
                    self.target(f, t, tt);
                }
                StmtKind::AugAssign(place, _, e) => {
                    // `xs += [3]` into a list
                    if !matches!(place.ty, Ty::Float) && self.tainted(f, e) {
                        self.place(f, place);
                    }
                }
                StmtKind::For(t, it, ..) => self.iter(f, t, it),
                StmtKind::Return(Some(e)) => {
                    if self.tainted(f, e) && self.t.rets.insert(self.cur) {
                        self.changed = true;
                    }
                }
                StmtKind::LetSome(v, e, _) if self.tainted(f, e) => self.mark_var(f, *v),
                _ => {}
            }
            crate::gen::stmt_exprs(s, &mut |e| self.expr(f, e));
            for b in s.blocks() {
                self.stmts(f, b);
            }
        }
    }

    /// An object shown as text shows its fields.
    fn shows_taint(&self, f: FuncId, e: &Expr) -> bool {
        self.tainted(f, e) || self.type_shows(&e.ty, &mut HashSet::new())
    }

    fn type_shows(&self, t: &Ty, seen: &mut HashSet<ClassId>) -> bool {
        match t {
            Ty::Class(c) | Ty::Obj(c) => {
                let c = *c;
                if !seen.insert(c) {
                    return false;
                }
                let cl = &self.p.classes[c];
                cl.method("__str__").is_none()
                    && cl.method("__repr__").is_none()
                    && cl.fields.iter().any(|fl| (has_float(&fl.ty) && self.field(c, &fl.name)) || self.type_shows(&fl.ty, seen))
            }
            Ty::List(e) | Ty::Set(e) | Ty::Optional(e) | Ty::Deque(e) => self.type_shows(e, seen),
            Ty::Dict(k, v, _) => self.type_shows(k, seen) || self.type_shows(v, seen),
            Ty::Tuple(ts) => ts.iter().any(|t| self.type_shows(t, seen)),
            _ => false,
        }
    }

    fn check(&self, f: FuncId, e: &Expr) -> Res<()> {
        use ExprKind as K;
        let bad = match &e.kind {
            K::Builtin("print" | "str" | "repr" | "json.dumps", args) => args.iter().any(|a| self.shows_taint(f, a)),
            K::FStr(parts) => parts.iter().any(|p| match p {
                FPart::Val(x, conv, spec) => {
                    let float_spec = spec.chars().last().is_some_and(|c| "eEfFgG%".contains(c)) && *conv != Some('r');
                    !float_spec && self.shows_taint(f, x)
                }
                FPart::Lit(_) => false,
            }),
            _ => false,
        };
        if bad {
            return err(e.line, "an int that went into a float is shown here: CPython keeps the int (`x: float = 3` prints 3, not 3.0)")
                .map_err(|x| x.hint("write a float where the int becomes a float: 3.0, or float(n)"));
        }
        let mut r = Ok(());
        e.children(&mut |c| {
            if r.is_ok() {
                r = self.check(f, c);
            }
        });
        r
    }

    fn check_stmts(&self, f: FuncId, body: &[Stmt]) -> Res<()> {
        for s in body {
            let mut r = Ok(());
            crate::gen::stmt_exprs(s, &mut |e| {
                if r.is_ok() {
                    r = self.check(f, e);
                }
            });
            r?;
            for b in s.blocks() {
                self.check_stmts(f, b)?;
            }
        }
        Ok(())
    }
}

/// Reject programs that show an int held in a float place.
pub fn check(p: &Program) -> Res<()> {
    let mut pass = Pass { p, t: Taint::default(), changed: true, cur: (p.main, 0) };
    // every function at least without maybe-int arguments (methods called implicitly)
    for f in 0..p.funcs.len() {
        pass.t.vars.insert((f, 0), HashSet::new());
    }
    while pass.changed {
        pass.changed = false;
        let ctxs: Vec<Ctx> = pass.t.vars.keys().copied().collect();
        for ctx in ctxs {
            pass.cur = ctx;
            let (f, mask) = ctx;
            for (i, v) in params_of(p, f).into_iter().enumerate().take(64) {
                if mask & (1 << i) != 0 {
                    pass.mark_var(f, v);
                }
            }
            pass.stmts(f, &p.funcs[f].body);
        }
    }
    let ctxs: Vec<Ctx> = pass.t.vars.keys().copied().collect();
    for ctx in ctxs {
        pass.cur = ctx;
        pass.check_stmts(ctx.0, &p.funcs[ctx.0].body)?;
    }
    Ok(())
}
