//! Calls of the packages implemented in Rust, through `rupy_lib.wasm` (see
//! [`super::bridge`]): a package function becomes a function that sends its
//! arguments to the host as tokens and reads its result back; a package
//! object is a struct (class id, handle).

use super::bridge;
use super::enc::{Block, Heap, Val};
use super::{unsupported, Fx, Res, H, W};
use crate::ir::*;

/// The package functions a program may call (importing a package declares
/// all of its functions; the others get no bridge code). Special methods are
/// called by printing, comparing and the like, so they count as used.
pub(crate) fn used_package_funcs(p: &Program) -> Vec<bool> {
    let mut seen = vec![false; p.funcs.len()];
    let mut work = vec![];
    for (i, f) in p.funcs.iter().enumerate() {
        let dunder = f.ext.is_some() && f.name.starts_with("__") && f.name.ends_with("__") && !f.is_init;
        if f.ext.is_none() || dunder {
            seen[i] = true;
            work.push(i);
        }
    }
    while let Some(f) = work.pop() {
        let mut found = vec![];
        fn ex(p: &Program, e: &Expr, found: &mut Vec<FuncId>) {
            match &e.kind {
                ExprKind::Call(f, _) | ExprKind::Method(_, f, _) | ExprKind::SuperInit(f, _) => found.push(*f),
                ExprKind::New(c, _) => found.extend(p.classes[*c].init),
                ExprKind::Field(o, name) => {
                    if let Ty::Class(c) | Ty::Obj(c) = &o.ty {
                        found.extend(p.classes[*c].method(name).filter(|m| p.funcs[*m].property));
                    }
                }
                _ => {}
            }
            e.children(&mut |c| ex(p, c, found));
        }
        fn st(p: &Program, s: &Stmt, found: &mut Vec<FuncId>) {
            crate::gen::stmt_exprs(s, &mut |e| ex(p, e, found));
            s.blocks().iter().for_each(|b| b.iter().for_each(|x| st(p, x, found)));
        }
        p.funcs[f].body.iter().for_each(|s| st(p, s, &mut found));
        found.extend(p.funcs[f].dispatch.iter().map(|(_, x)| *x));
        for g in found {
            if !seen[g] {
                seen[g] = true;
                work.push(g);
            }
        }
    }
    seen
}

/// Whether `e` makes a new package object (a call of the package, or an index).
pub(crate) fn is_fresh(p: &Program, e: &Expr) -> bool {
    let obj = matches!(&e.ty, Ty::Class(c) | Ty::Obj(c) if p.classes[*c].ext.is_some());
    obj && match &e.kind {
        ExprKind::Call(f, _) | ExprKind::Method(_, f, _) => p.funcs[*f].ext.is_some(),
        ExprKind::New(c, _) => p.classes[*c].ext.is_some(),
        ExprKind::Builtin("index", _) => true,
        _ => false,
    }
}

/// Local variables of `fid` that only ever hold new package objects and only
/// pass them to the package (or print them): nothing else holds their object,
/// so it can be freed when the variable gets another.
pub(crate) fn droppable_vars(p: &Program, fid: FuncId) -> std::collections::HashSet<VarId> {
    use std::collections::HashMap;
    let f = &p.funcs[fid];
    let mut out = std::collections::HashSet::new();
    if !f.captures.is_empty() || f.is_gen {
        return out;
    }
    let (mut uses, mut safe): (HashMap<VarId, usize>, HashMap<VarId, usize>) = (HashMap::new(), HashMap::new());
    let mut bad: std::collections::HashSet<VarId> = Default::default();
    let mut cand: std::collections::HashSet<VarId> = Default::default();
    fn ex(p: &Program, e: &Expr, safe_here: bool, uses: &mut HashMap<VarId, usize>, safe: &mut HashMap<VarId, usize>) {
        if let ExprKind::Var(v) = &e.kind {
            *uses.entry(*v).or_default() += 1;
            if safe_here {
                *safe.entry(*v).or_default() += 1;
            }
        }
        // the operands of a package call, of printing, of formatting: read only
        let safe_kids = match &e.kind {
            ExprKind::Call(f, _) | ExprKind::Method(_, f, _) => p.funcs[*f].ext.is_some(),
            ExprKind::Builtin(n, _) => matches!(*n, "print" | "str" | "repr" | "len" | "format" | "index"),
            ExprKind::FStr(_) => true,
            _ => false,
        };
        e.children(&mut |c| ex(p, c, safe_kids, uses, safe));
    }
    fn st(p: &Program, s: &Stmt, uses: &mut HashMap<VarId, usize>, safe: &mut HashMap<VarId, usize>, bad: &mut std::collections::HashSet<VarId>, cand: &mut std::collections::HashSet<VarId>) {
        match &s.kind {
            StmtKind::Assign(Target::Var(v), e) => {
                if is_fresh(p, e) {
                    cand.insert(*v);
                } else {
                    bad.insert(*v);
                }
            }
            StmtKind::Assign(t, _) | StmtKind::For(t, ..) => mark_targets(t, bad),
            StmtKind::AugVar(v, ..) | StmtKind::LetSome(v, ..) => {
                bad.insert(*v);
            }
            _ => {}
        }
        crate::gen::stmt_exprs(s, &mut |e| ex(p, e, false, uses, safe));
        s.blocks().iter().for_each(|b| b.iter().for_each(|x| st(p, x, uses, safe, bad, cand)));
    }
    fn mark_targets(t: &Target, bad: &mut std::collections::HashSet<VarId>) {
        match t {
            Target::Var(v) => {
                bad.insert(*v);
            }
            Target::Tuple(ts) => ts.iter().for_each(|t| mark_targets(t, bad)),
            Target::Place(_) => {}
        }
    }
    f.body.iter().for_each(|s| st(p, s, &mut uses, &mut safe, &mut bad, &mut cand));
    for v in cand {
        let local = f.vars[v].kind == VarKind::Local;
        if local && !bad.contains(&v) && uses.get(&v).copied().unwrap_or(0) == safe.get(&v).copied().unwrap_or(0) {
            out.insert(v);
        }
    }
    out
}

impl<'a> W<'a> {
    /// Free the package object in local `l` (of type `t`), if it holds one.
    pub fn free_obj(&mut self, l: u32, t: &Ty) -> Res<()> {
        let (Ty::Class(c) | Ty::Obj(c)) = t else { return Ok(()) };
        let (ct, free) = (self.class_ty[*c], self.host(H::Free));
        self.c().local_get(l).ref_is_null().i32_eqz().if_(Block::Empty);
        self.c().local_get(l).struct_get(ct, 1).local_get(l).struct_get(ct, 2).call(free).end();
        Ok(())
    }

    /// A call of package function `fi`: arguments that are new package
    /// objects (temporaries) are freed after it.
    pub fn pkg_call_freeing(&mut self, recv: Option<&Expr>, args: &[Expr], fi: u32) -> Res<()> {
        let mut temps = vec![];
        for a in recv.into_iter().chain(args) {
            self.expr(a)?;
            if is_fresh(self.p, a) {
                let v = self.val(&a.ty)?.unwrap();
                let l = self.fx.local(v);
                self.c().local_tee(l);
                temps.push((l, a.ty.clone()));
            }
        }
        self.c().call(fi);
        for (l, t) in temps {
            self.free_obj(l, &t)?;
        }
        Ok(())
    }

    /// The value of type `t` on the stack → its tokens, pushed to the host.
    pub fn push_tokens(&mut self, t: &Ty) -> Res<()> {
        let f = self.rt_push(t)?;
        if f != u32::MAX {
            self.c().call(f);
        }
        Ok(())
    }

    /// The function pushing a `t` (`u32::MAX`: `t` has no value).
    fn rt_push(&mut self, t: &Ty) -> Res<u32> {
        let Some(v) = self.val(t)? else { return Ok(u32::MAX) };
        let name = format!("push {}", TyName(t, self.p));
        let t = t.clone();
        self.rt_fn(&name, |w| {
            w.fx.params = vec![v];
            let int = w.host(H::IntArg);
            match &t {
                Ty::Int => {
                    w.c().local_get(0).call(int);
                }
                Ty::Float => {
                    let f = w.host(H::FloatArg);
                    w.c().local_get(0).call(f);
                }
                Ty::Bool => {
                    w.c().local_get(0).i64_extend_i32_u().call(int);
                }
                Ty::Str => {
                    let f = w.rt_str_arg()?;
                    w.c().local_get(0).call(f);
                }
                Ty::List(e) => {
                    let k = w.kind(e)?;
                    let lt = w.t.list[k as usize];
                    let i = w.fx.local(Val::I32);
                    w.c().local_get(0).struct_get(lt, 1).i64_extend_i32_s().call(int);
                    w.c().block(Block::Empty).loop_(Block::Empty);
                    w.c().local_get(i).local_get(0).struct_get(lt, 1).i32_ge_s().br_if(1);
                    w.c().local_get(0).local_get(i).i64_extend_i32_s();
                    w.list_get(e)?;
                    w.push_tokens(e)?;
                    w.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
                    w.c().end().end();
                }
                Ty::Tuple(ts) => {
                    let tt = w.tuple_ty(ts)?;
                    for (i, et) in ts.iter().enumerate() {
                        if w.val(et)?.is_some() {
                            w.c().local_get(0).struct_get(tt, i as u32);
                            w.push_tokens(et)?;
                        }
                    }
                }
                Ty::Optional(e) => {
                    w.c().local_get(0).ref_is_null().if_(Block::Empty).i64_const(0).call(int);
                    w.c().else_().i64_const(1).call(int).local_get(0);
                    w.unbox_opt(e)?;
                    w.push_tokens(e)?;
                    w.c().end();
                }
                Ty::Class(c) | Ty::Obj(c) if w.p.classes[*c].ext.is_some() => {
                    let ct = w.class_ty[*c];
                    w.c().local_get(0).struct_get(ct, 1).i64_extend_i32_s().call(int);
                }
                t => return unsupported(format!("passing {} to a package", TyName(t, w.p))),
            }
            Ok(vec![])
        })
    }

    /// Read a `t` from the host's result tokens → on the stack.
    pub fn pull_tokens(&mut self, t: &Ty) -> Res<()> {
        if self.val(t)?.is_none() {
            return Ok(());
        }
        let f = self.rt_pull(t)?;
        self.c().call(f);
        Ok(())
    }

    fn rt_pull(&mut self, t: &Ty) -> Res<u32> {
        let v = self.val(t)?.expect("a value");
        let name = format!("pull {}", TyName(t, self.p));
        let t = t.clone();
        self.rt_fn(&name, |w| {
            w.fx.params = vec![];
            let (int, float) = (w.host(H::RInt), w.host(H::RFloat));
            match &t {
                Ty::Int => {
                    w.c().call(int);
                }
                Ty::Float => {
                    w.c().call(float);
                }
                Ty::Bool => {
                    w.c().call(int).i64_eqz().i32_eqz();
                }
                Ty::Str => {
                    let (s, take) = (w.host(H::RStr), w.rt_take_str()?);
                    w.c().call(s).call(take);
                }
                Ty::List(e) => {
                    let k = w.kind(e)?;
                    let (new, app) = (w.rt_list_new(k)?, w.rt_list_append(k)?);
                    let lt = w.t.list[k as usize];
                    let (n, l) = (w.fx.local(Val::I32), w.fx.local(Val::Ref(Heap::Idx(lt))));
                    w.c().call(int).i32_wrap_i64().local_tee(n).call(new).local_set(l);
                    w.c().block(Block::Empty).loop_(Block::Empty);
                    w.c().local_get(n).i32_eqz().br_if(1);
                    w.c().local_get(l);
                    w.pull_tokens(e)?;
                    if w.val(e)?.is_none() {
                        w.c().i32_const(0);
                    }
                    w.c().call(app).local_get(n).i32_const(1).i32_sub().local_set(n).br(0);
                    w.c().end().end().local_get(l);
                }
                Ty::Tuple(ts) => {
                    let tt = w.tuple_ty(ts)?;
                    for et in ts {
                        w.pull_tokens(et)?;
                    }
                    w.c().struct_new(tt);
                }
                Ty::Optional(e) => {
                    let h = match v {
                        Val::Ref(h) | Val::NonNull(h) => h,
                        _ => unreachable!(),
                    };
                    w.c().call(int).i64_eqz().if_(Block::Val(v)).ref_null(h).else_();
                    w.pull_tokens(e)?;
                    w.box_opt(e)?;
                    w.c().end();
                }
                Ty::Dict(kt, vt, _) => {
                    let (kt, vt) = (kt.as_ref().clone(), vt.as_ref().clone());
                    w.dict_new(&kt)?;
                    let dt = w.t.dict;
                    let (n, d) = (w.fx.local(Val::I32), w.fx.local(Val::Ref(Heap::Idx(dt))));
                    w.c().local_set(d).call(int).i32_wrap_i64().local_set(n);
                    let set = w.rt_dict_set(&kt, &vt)?;
                    w.c().block(Block::Empty).loop_(Block::Empty);
                    w.c().local_get(n).i32_eqz().br_if(1);
                    w.c().local_get(d);
                    w.pull_tokens(&kt)?;
                    w.box_eq(&kt)?;
                    w.pull_tokens(&vt)?;
                    w.box_eq(&vt)?;
                    w.c().call(set).local_get(n).i32_const(1).i32_sub().local_set(n).br(0);
                    w.c().end().end().local_get(d);
                }
                Ty::Class(c) | Ty::Obj(c) if w.p.classes[*c].ext.is_some() => {
                    let (ct, track) = (w.class_ty[*c], w.host(H::Track));
                    let h = w.fx.local(Val::I32);
                    w.c().i32_const(*c as i32).call(int).i32_wrap_i64().local_tee(h).local_get(h).call(track).struct_new(ct);
                }
                t => return unsupported(format!("a package result of type {}", TyName(t, w.p))),
            }
            Ok(vec![v])
        })
    }

    /// Run package operation `key` on the arguments already pushed (after the key).
    fn pkg_call(&mut self) -> Res<()> {
        self.str_const("pkg");
        self.host_arg(&Ty::Str)?;
        let check = self.rt_host_check()?;
        let f = self.host(H::Call);
        self.c().call(f).call(check).drop();
        Ok(())
    }

    /// The function of package function `fid`: its arguments to the host, its result back.
    pub fn bridge_fn(&mut self, fid: FuncId) -> Res<()> {
        let f = &self.p.funcs[fid];
        let key = bridge::key(self.p, fid);
        self.fx = Fx { fid: Some(fid), ..Default::default() };
        // (type, local) of each value sent
        let mut sent: Vec<Ty> = vec![];
        let mut params = vec![];
        if !f.is_init {
            if let Some(sv) = f.self_var {
                let t = f.vars[sv].ty.clone();
                params.push(self.val(&t)?.unwrap());
                sent.push(t);
            }
        }
        for q in &f.params {
            if Some(q.var) == f.self_var {
                continue;
            }
            let t = f.vars[q.var].ty.clone();
            if let Some(v) = self.val(&t)? {
                params.push(v);
            }
            sent.push(t);
        }
        let ret = if f.is_init { Ty::Class(f.class.unwrap()) } else { f.ret.clone() };
        self.fx.params = params;
        self.str_const(&key);
        self.host_arg(&Ty::Str)?;
        let mut local = 0;
        for t in &sent {
            if self.val(t)?.is_some() {
                self.c().local_get(local);
                local += 1;
                self.push_tokens(t)?;
            }
        }
        self.pkg_call()?;
        self.pull_tokens(&ret)?;
        let results: Vec<Val> = self.val(&ret)?.into_iter().collect();
        let idx = self.user[fid];
        self.define(idx, results);
        Ok(())
    }

    /// `index` (a numpy-style index, `a[1:, 0]`): built by `rupy_lib.wasm`
    /// from the tagged parts (front's `index_arg`); a slice bound is sent as
    /// an optional int whatever its static type (`1`, `n`, absent).
    pub fn pkg_index(&mut self, args: &[Expr], t: &Ty) -> Res<()> {
        // the parts first, into locals: computing one may call a package,
        // which would take the arguments already pushed
        let mut locals: Vec<Option<u32>> = vec![];
        for a in args {
            match self.val(&a.ty)? {
                Some(v) if !matches!(a.kind, ExprKind::Str(_) | ExprKind::NoneVal) => {
                    self.expr(a)?;
                    let l = self.fx.local(v);
                    self.c().local_set(l);
                    locals.push(Some(l));
                }
                _ => locals.push(None),
            }
        }
        self.str_const(bridge::INDEX_KEY);
        self.host_arg(&Ty::Str)?;
        let int = self.host(H::IntArg);
        let mut i = 0;
        while i < args.len() {
            let ExprKind::Str(tag) = &args[i].kind else { return unsupported("this index") };
            let tag = tag.clone();
            self.str_const(&tag);
            self.push_tokens(&Ty::Str)?;
            i += 1;
            match tag.as_str() {
                "s" => {
                    for j in i..i + 3 {
                        match locals[j] {
                            None => {
                                self.c().i64_const(0).call(int);
                            }
                            Some(l) => {
                                self.c().local_get(l);
                                self.push_tokens(&args[j].ty)?;
                            }
                        }
                    }
                    i += 3;
                }
                "n" | "e" => {}
                _ => {
                    let Some(l) = locals[i] else { return unsupported("this index") };
                    self.c().local_get(l);
                    self.push_tokens(&args[i].ty)?;
                    i += 1;
                }
            }
        }
        self.pkg_call()?;
        self.pull_tokens(t)
    }
}
