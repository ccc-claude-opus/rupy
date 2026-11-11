//! `random`, `itertools` and `re` on the wasm backend. `random` is CPython's Mersenne
//! Twister in the host (`random.*` operations of rupy_wasm.mjs), so a seed gives
//! CPython's numbers; `choice`, `shuffle` and `sample` move the list's items here
//! with the host's indices. The `itertools` functions build their lists here, in
//! CPython's order. `re` runs in rupy_lib.wasm (the regex crate, as the native
//! backend); a compiled pattern and a match are the host's handles (i64).

use super::enc::{Block, Heap, Val};
use super::{Res, W};
use crate::ir::*;

impl<'a> W<'a> {
    /// Push the arguments `a` (of types `ts`) to the host: every one is evaluated
    /// first, since evaluating one may call the host, which takes the pushed ones.
    pub fn host_args(&mut self, a: &[Expr], ts: &[Ty]) -> Res<()> {
        let mut held = vec![];
        for (x, t) in a.iter().zip(ts) {
            let v = self.val(t)?.unwrap();
            let l = self.fx.local(v);
            self.expr(x)?;
            self.c().local_set(l);
            held.push(l);
        }
        for (l, t) in held.into_iter().zip(ts) {
            self.c().local_get(l);
            self.host_arg(t)?;
        }
        Ok(())
    }

    /// A list of `t` on the stack → (the list's local, its length's local (i32)).
    fn list_local(&mut self, t: &Ty) -> Res<(u32, u32)> {
        let k = self.kind(t)?;
        let lt = self.t.list[k as usize];
        let (l, n) = (self.fx.local(Val::Ref(Heap::Idx(lt))), self.fx.local(Val::I32));
        self.c().local_tee(l).struct_get(lt, 1).local_set(n);
        Ok((l, n))
    }

    /// The iterator argument `a` (`ExprKind::Iter`) as a list → (its local, its length's local, its element type).
    fn iter_list(&mut self, a: &Expr) -> Res<(u32, u32, Ty)> {
        let ExprKind::Iter(it) = &a.kind else { return super::unsupported("this argument") };
        let et = self.iter_ty(it)?;
        self.collect(it, &et)?;
        let (l, n) = self.list_local(&et)?;
        Ok((l, n, et))
    }

    /// The host's random index below `n` (an i32 local) → an i64 on the stack.
    fn randbelow(&mut self, n: u32) -> Res<()> {
        self.c().local_get(n).i64_extend_i32_s();
        self.host_arg(&Ty::Int)?;
        self.host_call("random.randbelow", &Ty::Int)
    }

    pub fn random_fn(&mut self, name: &str, a: &[Expr], _e: &Expr) -> Res<()> {
        match name {
            "random.seed" => {
                self.host_args(a, &[Ty::Int])?;
                self.host_call(name, &Ty::None)?;
            }
            "random.random" => self.host_call(name, &Ty::Float)?,
            "random.randint" | "random.randrange" => {
                self.host_args(a, &vec![Ty::Int; a.len()])?;
                self.host_call(name, &Ty::Int)?;
            }
            "random.uniform" => {
                self.host_args(a, &[Ty::Float, Ty::Float])?;
                self.host_call(name, &Ty::Float)?;
            }
            "random.choice" => {
                let Ty::List(et) = &a[0].ty else { return super::unsupported("choice() of this") };
                self.expr(&a[0])?;
                let (l, n) = self.list_local(et)?;
                self.c().local_get(n).i64_extend_i32_s();
                self.host_arg(&Ty::Int)?;
                self.host_call("random.choice", &Ty::Int)?; // IndexError when empty
                let i = self.fx.local(Val::I64);
                self.c().local_set(i).local_get(l).local_get(i);
                self.list_get(et)?;
            }
            "random.shuffle" => {
                // for i in reversed(range(1, n)): j = randbelow(i + 1); xs[i], xs[j] = xs[j], xs[i]
                let Ty::List(et) = &a[0].ty else { return super::unsupported("shuffle() of this") };
                let k = self.kind(et)?;
                self.expr(&a[0])?;
                let (l, n) = self.list_local(et)?;
                let (arr, lt) = (self.t.arr[k as usize], self.t.list[k as usize]);
                let (i, i1, j, tmp) = (self.fx.local(Val::I32), self.fx.local(Val::I32), self.fx.local(Val::I32), self.fx.local(self.kval_of(k)));
                self.c().local_get(n).i32_const(1).i32_sub().local_set(i);
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(i).i32_const(1).i32_lt_s().br_if(1);
                self.c().local_get(i).i32_const(1).i32_add().local_set(i1);
                self.randbelow(i1)?;
                self.c().i32_wrap_i64().local_set(j);
                self.c().local_get(l).struct_get(lt, 0).local_get(i).array_get(arr).local_set(tmp);
                self.c().local_get(l).struct_get(lt, 0).local_get(i).local_get(l).struct_get(lt, 0).local_get(j).array_get(arr).array_set(arr);
                self.c().local_get(l).struct_get(lt, 0).local_get(j).local_get(tmp).array_set(arr);
                self.c().local_get(i).i32_const(1).i32_sub().local_set(i).br(0);
                self.c().end().end();
            }
            "random.sample" => {
                // the host picks the k indices (CPython's set-or-pool selection)
                let (l, n, et) = self.iter_list(&a[0])?;
                let kk = self.fx.local(Val::I64);
                self.expr(&a[1])?;
                self.c().local_set(kk);
                self.c().local_get(n).i64_extend_i32_s();
                self.host_arg(&Ty::Int)?;
                self.c().local_get(kk);
                self.host_arg(&Ty::Int)?;
                self.host_call("random.sample", &Ty::None)?; // ValueError when k is out of range
                let k = self.kind(&et)?;
                let (new, app, get) = (self.rt_list_new(k)?, self.rt_list_append(k)?, self.rt_list_get(k)?);
                let out = self.fx.local(Val::Ref(Heap::Idx(self.t.list[k as usize])));
                let i = self.fx.local(Val::I32);
                self.c().local_get(kk).i32_wrap_i64().call(new).local_set(out);
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(i).i64_extend_i32_s().local_get(kk).i64_ge_s().br_if(1);
                self.c().local_get(out).local_get(l);
                self.c().local_get(i).i64_extend_i32_s();
                self.host_arg(&Ty::Int)?;
                self.host_call("random.sample_at", &Ty::Int)?;
                self.c().call(get).call(app);
                self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
                self.c().end().end().local_get(out);
            }
            _ => return super::unsupported(format!("`{}`", name)),
        }
        Ok(())
    }

    pub(crate) fn kval_of(&self, k: super::K) -> Val {
        match k {
            super::K::I64 => Val::I64,
            super::K::F64 => Val::F64,
            super::K::I32 => Val::I32,
            super::K::Ref => Val::Ref(Heap::Eq),
        }
    }

    pub fn itertools_fn(&mut self, name: &str, a: &[Expr], e: &Expr) -> Res<()> {
        let Ty::List(rt) = &e.ty else { return super::unsupported(format!("`{}`", name)) };
        let rk = self.kind(rt)?;
        let (new, app) = (self.rt_list_new(rk)?, self.rt_list_append(rk)?);
        let out = self.fx.local(Val::Ref(Heap::Idx(self.t.list[rk as usize])));
        self.c().i32_const(0).call(new).local_set(out);
        match name {
            "itertools.chain" => {
                let get = self.rt_list_get(rk)?;
                for x in a {
                    let (l, n, _) = self.iter_list(x)?;
                    let i = self.fx.local(Val::I32);
                    self.c().block(Block::Empty).loop_(Block::Empty);
                    self.c().local_get(i).local_get(n).i32_ge_s().br_if(1);
                    self.c().local_get(out).local_get(l).local_get(i).i64_extend_i32_s().call(get).call(app);
                    self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
                    self.c().end().end();
                }
            }
            "itertools.accumulate" => {
                let (l, n, et) = self.iter_list(&a[0])?;
                let v = self.val(&et)?.unwrap();
                let (acc, i) = (self.fx.local(v), self.fx.local(Val::I32));
                let add = if et == Ty::Int { Some(self.rt_int_add()?) } else { None };
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(i).local_get(n).i32_ge_s().br_if(1);
                // the first item as it is, then acc + item
                self.c().local_get(i).i32_eqz().if_(Block::Empty);
                self.c().local_get(l).local_get(i).i64_extend_i32_s();
                self.list_get(&et)?;
                self.c().local_set(acc);
                self.c().else_();
                self.c().local_get(acc).local_get(l).local_get(i).i64_extend_i32_s();
                self.list_get(&et)?;
                match add {
                    Some(f) => {
                        self.c().call(f);
                    }
                    None => {
                        self.c().f64_add();
                    }
                }
                self.c().local_set(acc).end();
                self.c().local_get(out).local_get(acc).call(app);
                self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
                self.c().end().end();
            }
            "itertools.pairwise" => {
                let (l, n, et) = self.iter_list(&a[0])?;
                let ts = vec![et.clone(), et.clone()];
                let tt = self.tuple_ty(&ts)?;
                let i = self.fx.local(Val::I32);
                self.c().i32_const(1).local_set(i);
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(i).local_get(n).i32_ge_s().br_if(1);
                self.c().local_get(out);
                self.c().local_get(l).local_get(i).i32_const(1).i32_sub().i64_extend_i32_s();
                self.list_get(&et)?;
                self.c().local_get(l).local_get(i).i64_extend_i32_s();
                self.list_get(&et)?;
                self.c().struct_new(tt).call(app);
                self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
                self.c().end().end();
            }
            "itertools.product" | "itertools.product_repeat" | "itertools.permutations" | "itertools.combinations" => {
                // nested loops over the lists, r deep, in CPython's (lexicographic) order
                let Ty::Tuple(ts) = rt.as_ref() else { return super::unsupported(format!("`{}`", name)) };
                let ts = ts.clone();
                let mut lists = vec![];
                if name == "itertools.product" {
                    for x in a {
                        let (l, n, _) = self.iter_list(x)?;
                        lists.push((l, n));
                    }
                } else {
                    let (l, n, _) = self.iter_list(&a[0])?;
                    lists = vec![(l, n); ts.len()];
                }
                let idx: Vec<u32> = (0..ts.len()).map(|_| self.fx.local(Val::I32)).collect();
                let tt = self.tuple_ty(&ts)?;
                self.nested(name, 0, &lists, &idx, &ts, tt, out, app)?;
            }
            _ => return super::unsupported(format!("`{}`", name)),
        }
        self.c().local_get(out);
        Ok(())
    }

    /// Loop `d` of the nested loops of `itertools_fn`; the innermost appends the tuple.
    #[allow(clippy::too_many_arguments)]
    fn nested(&mut self, name: &str, d: usize, lists: &[(u32, u32)], idx: &[u32], ts: &[Ty], tt: u32, out: u32, app: u32) -> Res<()> {
        if d == idx.len() {
            self.c().local_get(out);
            for (j, t) in ts.iter().enumerate() {
                self.c().local_get(lists[j].0).local_get(idx[j]).i64_extend_i32_s();
                self.list_get(t)?;
            }
            self.c().struct_new(tt).call(app);
            return Ok(());
        }
        let (i, n) = (idx[d], lists[d].1);
        if name == "itertools.combinations" && d > 0 {
            self.c().local_get(idx[d - 1]).i32_const(1).i32_add().local_set(i);
        } else {
            self.c().i32_const(0).local_set(i);
        }
        self.c().block(Block::Empty).loop_(Block::Empty);
        self.c().local_get(i).local_get(n).i32_ge_s().br_if(1);
        self.c().block(Block::Empty);
        if name == "itertools.permutations" {
            // skip a position an outer loop has
            for &o in &idx[..d] {
                self.c().local_get(i).local_get(o).i32_eq().br_if(0);
            }
        }
        self.nested(name, d + 1, lists, idx, ts, tt, out, app)?;
        self.c().end();
        self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
        self.c().end().end();
        Ok(())
    }

    /// A host result on the stack (i64: a handle, -1 for None) → `Match | None`.
    fn opt_handle(&mut self) {
        let b = self.t.box_i64;
        let v = self.fx.local(Val::I64);
        self.c().local_tee(v).i64_const(0).i64_lt_s();
        self.c().if_(Block::Val(Val::Ref(Heap::Idx(b)))).ref_null(Heap::Idx(b)).else_().local_get(v).struct_new(b).end();
    }

    /// A count from the host on the stack → a list of `t`, item i from host operation `op`(i).
    fn host_items(&mut self, op: &str, t: &Ty) -> Res<()> {
        let k = self.kind(t)?;
        let (new, app) = (self.rt_list_new(k)?, self.rt_list_append(k)?);
        let (n, i) = (self.fx.local(Val::I64), self.fx.local(Val::I64));
        let out = self.fx.local(Val::Ref(Heap::Idx(self.t.list[k as usize])));
        self.c().local_tee(n).i32_wrap_i64().call(new).local_set(out);
        self.c().block(Block::Empty).loop_(Block::Empty);
        self.c().local_get(i).local_get(n).i64_ge_s().br_if(1);
        self.c().local_get(out).local_get(i);
        self.host_arg(&Ty::Int)?;
        // a match is the host's handle, an int
        self.host_call(op, if matches!(t, Ty::Match(_)) { &Ty::Int } else { t })?;
        self.c().call(app);
        self.c().local_get(i).i64_const(1).i64_add().local_set(i).br(0);
        self.c().end().end().local_get(out);
        Ok(())
    }

    pub fn re_fn(&mut self, name: &str, a: &[Expr], e: &Expr) -> Res<()> {
        self.uses_lib = true;
        // a pattern method's receiver is the pattern's handle; a module function's, its text
        let p = if name.starts_with("re.p_") || name.starts_with("re.m_") { Ty::Int } else { Ty::Str };
        let (s, i) = (Ty::Str, Ty::Int);
        let host = name.replacen("re.p_", "re.", 1);
        match name {
            "re.compile" => {
                self.host_args(a, &[s.clone(), s])?;
                self.host_call(name, &i)?;
            }
            "re.search" | "re.match" | "re.fullmatch" | "re.p_search" | "re.p_match" | "re.p_fullmatch" => {
                self.host_args(a, &[p, s])?;
                self.host_call(&host, &i)?;
                self.opt_handle();
            }
            "re.findall" | "re.split" | "re.p_findall" | "re.p_split" => {
                self.host_args(a, &[p, s])?;
                self.host_call(&host, &Ty::list(Ty::Str))?;
            }
            "re.findall_groups" | "re.p_findall_groups" => {
                let Ty::List(row) = &e.ty else { return super::unsupported(name) };
                self.host_args(a, &[p, s])?;
                self.host_call(&host, &i)?;
                self.host_items("re.row", row)?;
            }
            "re.finditer" | "re.p_finditer" => {
                self.host_args(a, &[p, s])?;
                self.host_call(&host, &i)?;
                self.host_items("re.iter_at", &Ty::Match(0))?;
            }
            "re.sub" | "re.p_sub" => {
                self.host_args(a, &[p, s.clone(), s, i])?;
                self.host_call(&host, &Ty::Str)?;
            }
            "re.escape" => {
                self.host_args(a, &[s])?;
                self.host_call(name, &Ty::Str)?;
            }
            "re.m_group" | "re.m_start" | "re.m_end" => {
                self.host_args(a, &[i.clone(), i])?;
                self.host_call(name, if name == "re.m_group" { &Ty::Str } else { &Ty::Int })?;
            }
            "re.m_group_named" => {
                self.host_args(a, &[i, s])?;
                self.host_call(name, &Ty::Str)?;
            }
            "re.m_span" => {
                let (h, g) = (self.fx.local(Val::I64), self.fx.local(Val::I64));
                self.expr(&a[0])?;
                self.c().local_set(h);
                self.expr(&a[1])?;
                self.c().local_set(g);
                for op in ["re.m_start", "re.m_end"] {
                    self.c().local_get(h);
                    self.host_arg(&Ty::Int)?;
                    self.c().local_get(g);
                    self.host_arg(&Ty::Int)?;
                    self.host_call(op, &Ty::Int)?;
                }
                let tt = self.tuple_ty(&[Ty::Int, Ty::Int])?;
                self.c().struct_new(tt);
            }
            "re.m_groups" => {
                self.host_args(a, &[i])?;
                self.host_call(name, &e.ty)?;
            }
            _ => return super::unsupported(format!("`{}`", name)),
        }
        Ok(())
    }
}
