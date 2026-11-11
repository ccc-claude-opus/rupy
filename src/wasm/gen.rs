//! Generators on the wasm backend. A generator is a frame object: a subtype
//! of `gen_base[k]` (the resume function, the last yielded value, the state)
//! with a field for each local of the generator's code. `next` calls the
//! resume function, which loads the locals from the frame and runs the body
//! again from its start, skipping every statement until it reaches the
//! `yield` it stopped at (the state; 0: the start, -1: finished), as
//! Asyncify does: a statement runs when the body is not resuming, and a
//! statement that holds the `yield` is entered (an `if` takes the branch
//! that holds it, a loop enters its body without testing or advancing, a
//! `try` goes into the handler that holds it). A `yield` in `finally` code
//! resumes on the path without an exception. At a
//! `yield` the value and the state go into the frame, the locals are saved,
//! and the function returns 1; at the end (or `return`) it returns 0.

use super::enc::{Block, Comp, Heap, Storage, SubType, Val};
use super::stmt::Cursor;
use super::{unsupported, Lab, Res, K, W};
use crate::ir::*;
use std::collections::HashMap;

/// The generator being compiled: its locals and where its `yield`s are.
pub(crate) struct GenFx {
    /// the frame (as `gen_base`) and the state to resume at (0: not resuming)
    pub fr: u32,
    pub resume: u32,
    pub base: u32,
    /// the label of the block a `yield` leaves (to save the locals)
    pub suspend: u32,
    /// each statement holding `yield`s (by address): the first and last of their numbers
    pub ranges: HashMap<usize, (u32, u32)>,
}

/// Number the `yield`s of `b` in order: every statement that holds some gets
/// their range (the numbers of a statement's `yield`s are consecutive).
fn number_yields(b: &[Stmt], next: &mut u32, ranges: &mut HashMap<usize, (u32, u32)>) {
    for s in b {
        let lo = *next;
        if is_yield(s).is_some() {
            *next += 1;
        }
        for inner in s.blocks() {
            number_yields(inner, next, ranges);
        }
        if *next > lo {
            ranges.insert(s as *const Stmt as usize, (lo + 1, *next));
        }
    }
}

/// The value of a `yield` statement.
fn is_yield(s: &Stmt) -> Option<&Expr> {
    match &s.kind {
        StmtKind::Expr(Expr { kind: ExprKind::Builtin("yield", a), .. }) => a.first(),
        _ => None,
    }
}

const RESUME: u32 = 0;
const VAL: u32 = 1;
const STATE: u32 = 2;

impl<'a> W<'a> {
    /// `(ref null eq) -> i32`: the resume function of every generator.
    fn resume_ty(&mut self) -> u32 {
        self.m.func_ty(vec![Val::Ref(Heap::Eq)], vec![Val::I32])
    }

    /// The type of the generators of elements of kind `k`.
    pub fn gen_base(&mut self, k: K) -> u32 {
        if let Some(t) = self.gen_types.get(&k) {
            return *t;
        }
        let rt = self.resume_ty();
        let fields = vec![(Storage::Val(Val::Ref(Heap::Idx(rt))), false), (Storage::Val(self.kval_of(k)), true), (Storage::Val(Val::I32), true)];
        let t = self.m.ty(SubType { comp: Comp::Struct(fields), sup: None, open: true });
        self.gen_types.insert(k, t);
        t
    }

    /// The range of the `yield`s in `b` (statements of a generator), if any.
    fn block_range(&self, b: &[Stmt]) -> Option<(u32, u32)> {
        let g = self.fx.gen.as_ref()?;
        let rs: Vec<(u32, u32)> = b.iter().filter_map(|s| g.ranges.get(&(s as *const Stmt as usize)).copied()).collect();
        Some((rs.iter().map(|r| r.0).min()?, rs.iter().map(|r| r.1).max()?))
    }

    /// Push whether the generator resumes into `range` (false when it is None).
    fn resuming_into(&mut self, range: Option<(u32, u32)>) {
        let r = self.fx.gen.as_ref().unwrap().resume;
        match range {
            Some((lo, hi)) => {
                self.c().local_get(r).i32_const(lo as i32).i32_ge_u().i32_const(hi as i32).local_get(r).i32_ge_u().i32_and();
            }
            None => {
                self.c().i32_const(0);
            }
        }
    }

    /// A statement of a generator: it runs when the body is not resuming;
    /// one that holds the `yield` to resume at is entered.
    pub fn gen_stmt(&mut self, s: &Stmt) -> Res<()> {
        let g = self.fx.gen.as_ref().unwrap();
        let resume = g.resume;
        let range = g.ranges.get(&(s as *const Stmt as usize)).copied();
        self.c().local_get(resume).i32_eqz();
        if range.is_some() {
            self.resuming_into(range);
            self.c().i32_or();
        }
        self.c().if_(Block::Empty);
        self.labeled(Lab::Plain, |w| if range.is_some() { w.gen_enter(s) } else { w.stmt_kind(s) })?;
        self.c().end();
        Ok(())
    }

    /// A statement that holds `yield`s (resuming into it, or not resuming).
    fn gen_enter(&mut self, s: &Stmt) -> Res<()> {
        let g = self.fx.gen.as_ref().unwrap();
        let (fr, resume, base, suspend) = (g.fr, g.resume, g.base, g.suspend);
        if let Some(x) = is_yield(s) {
            let (lo, _) = g.ranges[&(s as *const Stmt as usize)];
            // resuming here: go on after it; else yield the value and leave
            self.c().local_get(resume).if_(Block::Empty);
            self.c().i32_const(0).local_set(resume);
            self.c().else_();
            self.labeled(Lab::Plain, |w| {
                w.c().local_get(fr);
                w.expr(x)?;
                if w.val(&x.ty)?.is_none() {
                    w.c().i32_const(0);
                }
                w.c().struct_set(base, VAL);
                w.c().local_get(fr).i32_const(lo as i32).struct_set(base, STATE);
                let d = w.fx.depth(Lab::Break(suspend));
                w.c().br(d);
                Ok(())
            })?;
            self.c().end();
            return Ok(());
        }
        match &s.kind {
            StmtKind::If(c, a, b) => {
                // resuming: the branch that holds the `yield`
                let ra = self.block_range(a);
                self.c().local_get(resume).if_(Block::Val(Val::I32));
                self.resuming_into(ra);
                self.c().else_();
                self.cond(c)?;
                self.c().end().if_(Block::Empty);
                self.labeled(Lab::Plain, |w| {
                    w.block(a)?;
                    if !b.is_empty() {
                        w.c().else_();
                        w.block(b)?;
                    }
                    Ok(())
                })?;
                self.c().end();
            }
            StmtKind::While(c, body, orelse) => {
                // resuming: into the body, without testing (or, into the `else` code: the
                // test is false)
                let rb = self.block_range(body);
                self.while_loop(body, orelse, |w| {
                    w.c().local_get(resume).if_(Block::Val(Val::I32));
                    w.resuming_into(rb);
                    w.c().else_();
                    w.cond(c)?;
                    w.c().end();
                    Ok(())
                })?;
            }
            StmtKind::For(t, it, body, orelse) => {
                let orelse_range = self.block_range(orelse);
                // resuming: the cursor is in the frame, and the body goes on with its item
                self.c().local_get(resume).i32_eqz().if_(Block::Empty);
                let mut cur = None;
                self.labeled(Lab::Plain, |w| {
                    cur = Some(w.iter_init(it)?);
                    Ok(())
                })?;
                self.c().end();
                let cur = cur.unwrap();
                self.for_loop(t, it, &cur, body, orelse, Some((resume, orelse_range)))?;
            }
            StmtKind::Try(_, hs, _, fin) => {
                // resuming in a handler: its body (the exception variable is in the
                // frame), then the `finally` code; else the whole statement (resuming in
                // the body, the `else` or the `finally` code goes there)
                let mut ends = 0;
                for h in hs {
                    let Some(r) = self.block_range(&h.body) else { continue };
                    self.resuming_into(Some(r));
                    self.c().if_(Block::Empty);
                    self.labeled(Lab::Plain, |w| w.try_stmt(&h.body, &[], &[], fin))?;
                    self.c().else_();
                    self.fx.labels.push(Lab::Plain);
                    ends += 1;
                }
                self.stmt_kind(s)?;
                for _ in 0..ends {
                    self.fx.labels.pop();
                    self.c().end();
                }
            }
            _ => return unsupported("`yield` in this statement"),
        }
        Ok(())
    }

    /// `return` in a generator: it is finished.
    pub fn gen_return(&mut self) -> Res<()> {
        self.run_finals(0)?;
        let g = self.fx.gen.as_ref().unwrap();
        let (fr, base) = (g.fr, g.base);
        self.c().local_get(fr).i32_const(-1).struct_set(base, STATE).i32_const(0).return_();
        Ok(())
    }

    /// A generator function: its resume function and the function that makes its frame.
    pub fn gen_func(&mut self, fid: FuncId) -> Res<()> {
        let f = &self.p.funcs[fid];
        if f.self_var.is_some() {
            return unsupported("generator methods");
        }
        if !super::out_params(f).is_empty() {
            return unsupported("a generator that rebinds a variable of the enclosing function (nonlocal)");
        }
        let Ty::Gen(et) = &f.ret else { return unsupported("this generator") };
        let k = self.kind(et)?;
        let base = self.gen_base(k);
        let resume_fn = self.reserve();
        self.m.declared.push(resume_fn);
        let body = f.body.clone();
        let mut ranges = HashMap::new();
        number_yields(&body, &mut 0, &mut ranges);

        // the resume function: every variable is a local (saved in the frame)
        self.fx = super::Fx { fid: Some(fid), ..Default::default() };
        self.fx.params = vec![Val::Ref(Heap::Eq)];
        let fr = self.fx.local(Val::Ref(Heap::Idx(base)));
        let resume = self.fx.local(Val::I32);
        let mut param_locals = vec![];
        for (i, v) in f.vars.iter().enumerate() {
            if let Some(t) = self.val(&v.ty)? {
                let l = self.fx.local(t);
                self.fx.vars.insert(i, l);
            }
        }
        for q in &f.params {
            if let Some(&l) = self.fx.vars.get(&q.var) {
                param_locals.push(l);
            }
        }
        let suspend = self.fx.next_label + 1;
        self.fx.next_label += 1;
        self.fx.gen = Some(GenFx { fr, resume, base, suspend, ranges });
        self.c().block(Block::Empty);
        self.labeled(Lab::Break(suspend), |w| {
            w.block(&body)?;
            w.gen_return()
        })?;
        self.c().end();
        let body_code = std::mem::take(&mut self.fx.code.0);

        // the frame: the base fields, then every local but the frame's own
        let saved: Vec<(u32, Val)> = self.fx.locals.iter().enumerate().map(|(i, v)| (i as u32 + 1, *v)).filter(|(l, _)| *l != fr).collect();
        let mut fields = vec![(Storage::Val(Val::Ref(Heap::Idx(self.resume_ty()))), false), (Storage::Val(self.kval_of(k)), true), (Storage::Val(Val::I32), true)];
        fields.extend(saved.iter().map(|(_, v)| (Storage::Val(*v), true)));
        let frame = self.m.ty(SubType { comp: Comp::Struct(fields), sup: Some(base), open: false });
        let frl = self.fx.local(Val::Ref(Heap::Idx(frame)));
        // prologue: finished → 0; else load the locals and the state
        self.c().local_get(0).ref_cast(Heap::Idx(base)).local_set(fr);
        self.c().local_get(fr).struct_get(base, STATE).i32_const(-1).i32_eq().if_(Block::Empty).i32_const(0).return_().end();
        self.c().local_get(0).ref_cast(Heap::Idx(frame)).local_set(frl);
        for (j, (l, _)) in saved.iter().enumerate() {
            self.c().local_get(frl).struct_get(frame, 3 + j as u32).local_set(*l);
        }
        self.c().local_get(fr).struct_get(base, STATE).local_set(resume);
        self.fx.code.0.extend(body_code);
        // suspended at a `yield`: save the locals
        for (j, (l, _)) in saved.iter().enumerate() {
            self.c().local_get(frl).local_get(*l).struct_set(frame, 3 + j as u32);
        }
        self.c().i32_const(1);
        self.define(resume_fn, vec![Val::I32]);

        // the generator function: a new frame, its parameters in their fields
        self.fx = super::Fx::default();
        let mut params = vec![];
        for q in &f.params {
            if let Some(v) = self.val(&f.vars[q.var].ty)? {
                params.push(v);
            }
        }
        self.fx.params = params;
        self.c().ref_func(resume_fn);
        let kv = self.kval_of(k);
        self.zero(kv);
        self.c().i32_const(0);
        for (l, v) in &saved {
            match param_locals.iter().position(|p| p == l) {
                Some(i) => {
                    self.c().local_get(i as u32);
                }
                None => self.zero(*v),
            }
        }
        self.c().struct_new(frame);
        let idx = self.user[fid];
        self.define(idx, vec![Val::Ref(Heap::Idx(base))]);
        Ok(())
    }

    /// The cursor of a generator value (on the stack).
    pub fn gen_cursor(&mut self, t: &Ty) -> Res<Cursor> {
        let k = self.kind(t)?;
        let base = self.gen_base(k);
        let g = self.fx.local(Val::Ref(Heap::Idx(base)));
        self.c().local_set(g);
        Ok(Cursor::Gen { g, base, ty: t.clone() })
    }

    /// The next item of generator `g` (a local of type `base`) → its value; `exit` when it is finished.
    pub fn gen_next_or(&mut self, g: u32, base: u32, t: &Ty, exit: u32) -> Res<()> {
        let rt = self.resume_ty();
        self.c().local_get(g).local_get(g).struct_get(base, RESUME).call_ref(rt).i32_eqz().br_if(exit);
        self.gen_value(g, base, t)
    }

    fn gen_value(&mut self, g: u32, base: u32, t: &Ty) -> Res<()> {
        self.c().local_get(g).struct_get(base, VAL);
        match self.val(t)? {
            Some(Val::Ref(h)) | Some(Val::NonNull(h)) => {
                self.c().ref_cast(h);
            }
            Some(_) => {}
            None => {
                self.c().drop();
            }
        }
        Ok(())
    }

    /// `next(g)` (StopIteration when it is finished) and `next(g, default)`.
    pub fn gen_next(&mut self, a: &[Expr], e: &Expr) -> Res<()> {
        let Ty::Gen(t) = &a[0].ty else { return unsupported("next() of this") };
        let k = self.kind(t)?;
        let base = self.gen_base(k);
        let g = self.fx.local(Val::Ref(Heap::Idx(base)));
        self.expr(&a[0])?;
        self.c().local_set(g);
        let rt = self.resume_ty();
        let v = self.val(&e.ty)?;
        self.c().local_get(g).local_get(g).struct_get(base, RESUME).call_ref(rt);
        self.c().if_(v.map_or(Block::Empty, Block::Val));
        self.gen_value(g, base, t)?;
        self.c().else_();
        self.labeled(Lab::Plain, |w| match a.get(1) {
            Some(d) => w.expr(d),
            None => w.raise_msg("StopIteration", ""),
        })?;
        self.c().end();
        Ok(())
    }
}
