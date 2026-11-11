//! Functions as values on the wasm backend. A `Callable` value is a closure: a
//! struct whose first field is a reference to a function taking the closure
//! itself and the arguments, a subtype of the closure type of its signature
//! with a field for each variable it captures. Each lambda (a function used as
//! a value is a lambda that calls it) becomes such a function; the variables
//! it captures are copied when the closure is made (the translator only takes
//! programs where that is the same as Python's reading them later).

use super::enc::{Comp, Heap, Storage, SubType, Val};
use super::{unsupported, Res, W};
use crate::ir::*;

/// The variables `e` reads, but those that lambdas inside it bind.
fn reads(e: &Expr, out: &mut Vec<VarId>, bound: &mut Vec<VarId>) {
    match &e.kind {
        ExprKind::Var(v) => {
            if !out.contains(v) {
                out.push(*v);
            }
        }
        ExprKind::Lambda(ps, b) => {
            bound.extend(ps);
            reads(b, out, bound);
        }
        _ => e.children(&mut |c| reads(c, out, bound)),
    }
}

impl<'a> W<'a> {
    /// The function type of closures of signature `ps -> r`: (closure, params...) -> r.
    fn closure_fn_ty(&mut self, ps: &[Ty], r: &Ty) -> Res<u32> {
        let mut params = vec![Val::Ref(Heap::Eq)];
        for p in ps {
            params.extend(self.val(p)?);
        }
        let results: Vec<Val> = self.val(r)?.into_iter().collect();
        Ok(self.m.func_ty(params, results))
    }

    /// The closure type of signature `ps -> r`: { fn }.
    pub fn closure_ty(&mut self, ps: &[Ty], r: &Ty) -> Res<u32> {
        let ft = self.closure_fn_ty(ps, r)?;
        Ok(self.m.ty(SubType { comp: Comp::Struct(vec![(Storage::Val(Val::Ref(Heap::Idx(ft))), false)]), sup: None, open: true }))
    }

    /// A lambda as a value (of type `Callable[ps, r]`): a closure of the variables it reads.
    pub fn closure(&mut self, params: &[VarId], body: &Expr, t: &Ty) -> Res<()> {
        let Ty::Func(ps, r) = t else { return unsupported("this lambda") };
        let fid = self.fx.fid.ok_or_else(|| "a lambda outside a function".to_string())?;
        let f = &self.p.funcs[fid];
        let (mut read, mut bound) = (vec![], params.to_vec());
        reads(body, &mut read, &mut bound);
        // captured: the variables it reads that are not its parameters (and have a value)
        let mut caps = vec![];
        for v in read {
            if bound.contains(&v) {
                continue;
            }
            if let Some(val) = self.val(&f.vars[v].ty)? {
                caps.push((v, val));
            }
        }
        let base = self.closure_ty(ps, r)?;
        let ft = self.closure_fn_ty(ps, r)?;
        let mut fields = vec![(Storage::Val(Val::Ref(Heap::Idx(ft))), false)];
        fields.extend(caps.iter().map(|(_, v)| (Storage::Val(*v), false)));
        let ct = self.m.ty(SubType { comp: Comp::Struct(fields), sup: Some(base), open: false });

        // the function: (closure, params...) → its body's value
        let idx = self.reserve();
        self.m.declared.push(idx);
        let saved = std::mem::take(&mut self.fx);
        self.fx = super::Fx { fid: Some(fid), ..Default::default() };
        let mut pv = vec![Val::Ref(Heap::Eq)];
        for v in params {
            if let Some(val) = self.val(&f.vars[*v].ty)? {
                self.fx.vars.insert(*v, pv.len() as u32);
                pv.push(val);
            }
        }
        self.fx.params = pv;
        let me = self.fx.local(Val::Ref(Heap::Idx(ct)));
        self.c().local_get(0).ref_cast(Heap::Idx(ct)).local_set(me);
        for (j, (v, val)) in caps.iter().enumerate() {
            let l = self.fx.local(*val);
            self.fx.vars.insert(*v, l);
            self.c().local_get(me).struct_get(ct, 1 + j as u32).local_set(l);
        }
        let ret = self.val(r)?;
        let r = (**r).clone();
        let res = (|| -> Res<()> {
            self.expr(body)?;
            match (self.val(&body.ty)?, ret) {
                (Some(_), None) => {
                    self.c().drop();
                }
                (None, Some(v)) => self.zero(v),
                _ => {}
            }
            if body.ty == Ty::Int && r == Ty::Float {
                self.c().f64_convert_i64_s();
            }
            Ok(())
        })();
        if let Err(e) = res {
            self.fx = saved;
            return Err(e);
        }
        self.define(idx, ret.into_iter().collect());
        self.fx = saved;

        // the closure: the function, then the captured values
        self.c().ref_func(idx);
        for (v, _) in &caps {
            let l = *self.fx.vars.get(v).ok_or_else(|| "a captured variable without a local".to_string())?;
            self.c().local_get(l);
        }
        self.c().struct_new(ct);
        Ok(())
    }

    /// `functools.reduce(f, iterable[, initial])`: `f` is a lambda of two parameters
    /// (the translator makes one of a function), run in place for each item.
    pub fn reduce(&mut self, a: &[Expr], e: &Expr) -> Res<()> {
        use super::enc::Block;
        let ExprKind::Lambda(ps, body) = &a[0].kind else { return unsupported("reduce() of this") };
        if ps.len() != 2 {
            return unsupported("reduce() of this");
        }
        let (l, n, et) = self.iter_list(&a[1])?;
        let av = self.val(&e.ty)?.unwrap();
        let (acc, i) = (self.fx.local(av), self.fx.local(Val::I32));
        match a.get(2) {
            Some(init) => {
                self.expr(init)?;
                self.c().local_set(acc);
            }
            None => {
                // the first item (TypeError when there is none)
                self.c().local_get(n).i32_eqz().if_(Block::Empty);
                self.throw_lit("TypeError", "reduce() of empty iterable with no initial value");
                self.c().end().local_get(l).i64_const(0);
                self.list_get(&et)?;
                self.c().local_set(acc).i32_const(1).local_set(i);
            }
        }
        let (pa, px) = (self.fx.vars.get(&ps[0]).copied(), self.fx.vars.get(&ps[1]).copied());
        self.c().block(Block::Empty).loop_(Block::Empty);
        self.fx.labels.extend([super::Lab::Plain, super::Lab::Plain]);
        self.c().local_get(i).local_get(n).i32_ge_s().br_if(1);
        if let Some(pa) = pa {
            self.c().local_get(acc).local_set(pa);
        }
        if let Some(px) = px {
            self.c().local_get(l).local_get(i).i64_extend_i32_s();
            self.list_get(&et)?;
            self.c().local_set(px);
        }
        self.expr(body)?;
        if body.ty == Ty::Int && e.ty == Ty::Float {
            self.c().f64_convert_i64_s();
        }
        self.c().local_set(acc);
        self.fx.labels.truncate(self.fx.labels.len() - 2);
        self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
        self.c().end().end().local_get(acc);
        Ok(())
    }

    /// `f(args)` of a Callable value `a[0]`.
    pub fn call_fn(&mut self, a: &[Expr]) -> Res<()> {
        let Ty::Func(ps, r) = &a[0].ty else { return unsupported("calling this") };
        let (base, ft) = (self.closure_ty(ps, r)?, self.closure_fn_ty(ps, r)?);
        let c = self.fx.local(Val::Ref(Heap::Idx(base)));
        self.expr(&a[0])?;
        self.c().local_tee(c);
        for x in &a[1..] {
            self.expr(x)?;
        }
        self.c().local_get(c).struct_get(base, 0).call_ref(ft);
        Ok(())
    }
}
