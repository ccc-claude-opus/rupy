//! `collections` (defaultdict, Counter, deque), `heapq` and `bisect` on the wasm
//! backend. A deque is a list (the same representation; `popleft` moves the
//! items); a Counter is a dict of ints. `heapq` sifts as CPython's does, so a
//! heap's list is CPython's.

use super::enc::{Block, Heap, Val};
use super::{unsupported, Lab, Res, K, W};
use crate::ir::*;

/// An int literal (an argument made here).
fn int(i: i64) -> Expr {
    Expr { id: 0, line: 0, ty: Ty::Int, kind: ExprKind::Int(i) }
}

impl<'a> W<'a> {
    pub fn collections_fn(&mut self, name: &str, a: &[Expr], e: &Expr) -> Res<()> {
        match name {
            "collections.defaultdict" => {
                let Ty::Dict(k, _, _) = &e.ty else { return unsupported(name) };
                self.dict_new(k)?;
            }
            "collections.Counter" => {
                let Ty::Dict(k, _, _) = &e.ty else { return unsupported(name) };
                let k = k.as_ref().clone();
                self.dict_new(&k)?;
                if let Some(it) = a.first() {
                    let d = self.fx.local(Val::Ref(Heap::Idx(self.t.dict)));
                    self.c().local_set(d);
                    self.count_into(d, it, &k)?;
                    self.c().local_get(d);
                }
            }
            "counter.update" => {
                let Ty::Dict(k, _, _) = &a[0].ty else { return unsupported(name) };
                let k = k.as_ref().clone();
                let d = self.fx.local(Val::Ref(Heap::Idx(self.t.dict)));
                self.expr(&a[0])?;
                self.c().local_set(d);
                self.count_into(d, &a[1], &k)?;
            }
            "counter.total" => {
                let (d, ae) = (self.t.dict, self.t.arr[3]);
                let (m, i, n) = (self.fx.local(Val::Ref(Heap::Idx(d))), self.fx.local(Val::I32), self.fx.local(Val::I64));
                self.expr(&a[0])?;
                self.c().local_set(m);
                let next = self.rt_dict_next()?;
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(m).local_get(i).call(next).local_tee(i).i32_const(0).i32_lt_s().br_if(1);
                self.c().local_get(n).local_get(m).struct_get(d, 1).local_get(i).array_get(ae);
                self.unbox_eq(&Ty::Int)?;
                self.c().i64_add().local_set(n);
                self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
                self.c().end().end().local_get(n);
            }
            "counter.elements" => {
                // each key, as many times as its count, in insertion order
                let Ty::Dict(kt, _, _) = &a[0].ty else { return unsupported(name) };
                let kk = self.kind(kt)?;
                let (d, ae) = (self.t.dict, self.t.arr[3]);
                let (new, app) = (self.rt_list_new(kk)?, self.rt_list_append(kk)?);
                let (m, i, c, out) = (self.fx.local(Val::Ref(Heap::Idx(d))), self.fx.local(Val::I32), self.fx.local(Val::I64), self.fx.local(Val::Ref(Heap::Idx(self.t.list[kk as usize]))));
                let kv = self.kval_of(kk);
                let key = self.fx.local(kv);
                self.expr(&a[0])?;
                self.c().local_set(m).i32_const(0).call(new).local_set(out);
                let next = self.rt_dict_next()?;
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(m).local_get(i).call(next).local_tee(i).i32_const(0).i32_lt_s().br_if(1);
                self.c().local_get(m).struct_get(d, 1).local_get(i).array_get(ae);
                self.unbox_eq(&Ty::Int)?;
                self.c().local_set(c);
                self.c().local_get(m).struct_get(d, 0).local_get(i).array_get(ae);
                self.unbox_eq(kt)?;
                self.c().local_set(key);
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(c).i64_const(0).i64_le_s().br_if(1);
                self.c().local_get(out).local_get(key).call(app);
                self.c().local_get(c).i64_const(1).i64_sub().local_set(c).br(0);
                self.c().end().end();
                self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
                self.c().end().end().local_get(out);
            }
            "counter.most_common" => {
                let Ty::Dict(kt, _, _) = &a[0].ty else { return unsupported(name) };
                let kt = kt.as_ref().clone();
                let f = self.rt_most_common(&kt)?;
                let lt = self.t.list[K::Ref as usize];
                let (l, n) = (self.fx.local(Val::Ref(Heap::Idx(lt))), self.fx.local(Val::I64));
                self.expr(&a[0])?;
                self.c().call(f).local_set(l);
                self.expr(&a[1])?;
                self.c().local_tee(n);
                // most_common(n): the first n (n < 0: all)
                self.c().i64_const(0).i64_ge_s().local_get(n).local_get(l).struct_get(lt, 1).i64_extend_i32_s().i64_lt_s().i32_and().if_(Block::Empty);
                self.c().local_get(l).local_get(n).i32_wrap_i64().struct_set(lt, 1).end();
                self.c().local_get(l);
            }
            "collections.deque" => {
                let Ty::Deque(t) = &e.ty else { return unsupported(name) };
                let k = self.kind(t)?;
                match a.first() {
                    None => {
                        let new = self.rt_list_new(k)?;
                        self.c().i32_const(0).call(new);
                    }
                    Some(x) => {
                        let ExprKind::Iter(it) = &x.kind else { return unsupported(name) };
                        self.collect(it, t)?;
                        // a new list (collect may give the iterable itself)
                        let copy = self.rt_list_slice(k)?;
                        self.c().i64_const(0).i32_const(0).i64_const(0).i32_const(0).i64_const(0).i32_const(0).call(copy);
                    }
                }
            }
            "deque.append" | "deque.extend" | "deque.clear" => self.list_method(&name[6..], a, e)?,
            "deque.appendleft" => self.list_method("insert", &[a[0].clone(), int(0), a[1].clone()], e)?,
            "deque.pop" | "deque.popleft" => {
                let Ty::Deque(t) = &a[0].ty else { return unsupported(name) };
                let lt = self.t.list[self.kind(t)? as usize];
                let l = self.fx.local(Val::Ref(Heap::Idx(lt)));
                self.expr(&a[0])?;
                self.c().local_tee(l).struct_get(lt, 1).i32_eqz().if_(Block::Empty);
                self.labeled(Lab::Plain, |w| w.raise_msg("IndexError", "pop from an empty deque"))?;
                self.c().end();
                let d = super::expr::local_expr_ty(l, &a[0].ty);
                if name == "deque.pop" {
                    self.list_method("pop", &[d], e)?;
                } else {
                    self.list_method("pop_at", &[d, int(0)], e)?;
                }
            }
            "heapq.heappush" | "heapq.heappop" | "heapq.heapify" | "heapq.heapreplace" | "heapq.heappushpop" => self.heap_fn(name, a)?,
            "bisect.bisect_left" | "bisect.bisect_right" | "bisect.insort_left" | "bisect.insort_right" => {
                let Ty::List(t) = &a[0].ty else { return unsupported(name) };
                let t = t.as_ref().clone();
                let k = self.kind(&t)?;
                let lt = self.t.list[k as usize];
                let f = self.rt_bisect(&t, name.ends_with("left"))?;
                let l = self.fx.local(Val::Ref(Heap::Idx(lt)));
                let xv = self.val(&t)?.unwrap_or(Val::I32);
                let x = self.fx.local(xv);
                self.expr(&a[0])?;
                self.c().local_set(l);
                self.expr(&a[1])?;
                self.c().local_set(x).local_get(l).local_get(x).call(f);
                if name.starts_with("bisect.insort") {
                    let i = self.fx.local(Val::I64);
                    let ins = self.rt_list_insert(k)?;
                    self.c().local_set(i).local_get(l).local_get(i).local_get(x).call(ins);
                }
            }
            "heapq.nlargest" | "heapq.nsmallest" => {
                // sorted(iterable, reverse=nlargest)[:n], as CPython documents
                let Ty::List(t) = &e.ty else { return unsupported(name) };
                let ExprKind::Iter(it) = &a[1].kind else { return unsupported(name) };
                let t = t.as_ref().clone();
                let k = self.kind(&t)?;
                let lt = self.t.list[k as usize];
                let (l, n) = (self.fx.local(Val::Ref(Heap::Idx(lt))), self.fx.local(Val::I64));
                self.expr(&a[0])?;
                self.c().local_set(n);
                self.collect(it, &t)?;
                let copy = self.rt_list_slice(k)?;
                self.c().i64_const(0).i32_const(0).i64_const(0).i32_const(0).i64_const(0).i32_const(0).call(copy).local_set(l);
                let none = Expr { id: 0, line: 0, ty: Ty::None, kind: ExprKind::NoneLit };
                self.sort_list(l, &t, &none, name == "heapq.nlargest")?;
                self.c().local_get(n).i64_const(0).i64_lt_s().if_(Block::Empty).i64_const(0).local_set(n).end();
                self.c().local_get(n).local_get(l).struct_get(lt, 1).i64_extend_i32_s().i64_lt_s().if_(Block::Empty);
                self.c().local_get(l).local_get(n).i32_wrap_i64().struct_set(lt, 1).end();
                self.c().local_get(l);
            }
            _ => return unsupported(format!("`{}`", name)),
        }
        Ok(())
    }

    /// Count the items of iterator argument `it` into Counter `d` (a local).
    fn count_into(&mut self, d: u32, it: &Expr, kt: &Ty) -> Res<()> {
        let (l, n, et) = self.iter_list(it)?;
        let get = self.rt_dict_get_default(kt, &Ty::Int, DK::Counter)?;
        let set = self.rt_dict_set(kt, &Ty::Int)?;
        let (i, key) = (self.fx.local(Val::I32), self.fx.local(Val::Ref(Heap::Eq)));
        self.c().block(Block::Empty).loop_(Block::Empty);
        self.c().local_get(i).local_get(n).i32_ge_s().br_if(1);
        self.c().local_get(l).local_get(i).i64_extend_i32_s();
        self.list_get(&et)?;
        self.box_eq(kt)?;
        self.c().local_set(key).local_get(d).local_get(key).local_get(d).local_get(key).call(get);
        self.unbox_eq(&Ty::Int)?;
        self.c().i64_const(1).i64_add();
        self.box_eq(&Ty::Int)?;
        self.c().call(set);
        self.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
        self.c().end().end();
        Ok(())
    }

    /// most_common(d) → list[tuple[key, int]], by count, most first (ties in insertion order).
    pub fn rt_most_common(&mut self, kt: &Ty) -> Res<u32> {
        let tt = self.tuple_ty(&[kt.clone(), Ty::Int])?;
        let (new, app) = (self.rt_list_new(K::Ref)?, self.rt_list_append(K::Ref)?);
        let next = self.rt_dict_next()?;
        let kt = kt.clone();
        self.rt_fn(&format!("most_common:{:?}", kt), |w| {
            let (d, ae) = (w.t.dict, w.t.arr[3]);
            let (lt, arr) = (w.t.list[K::Ref as usize], w.t.arr[K::Ref as usize]);
            w.fx.params = vec![Val::Ref(Heap::Idx(d))];
            let (out, i, j, x) = (w.fx.local(Val::Ref(Heap::Idx(lt))), w.fx.local(Val::I32), w.fx.local(Val::I32), w.fx.local(Val::Ref(Heap::Eq)));
            w.c().i32_const(0).call(new).local_set(out);
            w.c().block(Block::Empty).loop_(Block::Empty);
            w.c().local_get(0).local_get(i).call(next).local_tee(i).i32_const(0).i32_lt_s().br_if(1);
            w.c().local_get(out).local_get(0).struct_get(d, 0).local_get(i).array_get(ae);
            w.unbox_eq(&kt)?;
            w.c().local_get(0).struct_get(d, 1).local_get(i).array_get(ae);
            w.unbox_eq(&Ty::Int)?;
            w.c().struct_new(tt).call(app);
            w.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
            w.c().end().end();
            // insertion sort, stable: move an item left past the ones with smaller counts
            let count = |w: &mut W, at: u32| {
                w.c().local_get(out).struct_get(lt, 0).local_get(at).array_get(arr).ref_cast(Heap::Idx(tt)).struct_get(tt, 1);
            };
            w.c().i32_const(1).local_set(i);
            w.c().block(Block::Empty).loop_(Block::Empty);
            w.c().local_get(i).local_get(out).struct_get(lt, 1).i32_ge_s().br_if(1);
            w.c().local_get(out).struct_get(lt, 0).local_get(i).array_get(arr).local_set(x).local_get(i).local_set(j);
            w.c().block(Block::Empty).loop_(Block::Empty);
            w.c().local_get(j).i32_eqz().br_if(1);
            w.c().local_get(j).i32_const(1).i32_sub().local_set(j);
            count(w, j);
            w.c().local_get(x).ref_cast(Heap::Idx(tt)).struct_get(tt, 1).i64_ge_s();
            w.c().if_(Block::Empty).local_get(j).i32_const(1).i32_add().local_set(j).br(2).end();
            w.c().local_get(out).struct_get(lt, 0).local_get(j).i32_const(1).i32_add().local_get(out).struct_get(lt, 0).local_get(j).array_get(arr).array_set(arr);
            w.c().br(0);
            w.c().end().end();
            w.c().local_get(out).struct_get(lt, 0).local_get(j).local_get(x).array_set(arr);
            w.c().local_get(i).i32_const(1).i32_add().local_set(i).br(0);
            w.c().end().end().local_get(out);
            Ok(vec![Val::Ref(Heap::Idx(lt))])
        })
    }

    /// bisect_left / bisect_right(xs, x) → i64, by CPython's binary search.
    fn rt_bisect(&mut self, t: &Ty, left: bool) -> Res<u32> {
        let k = self.kind(t)?;
        let cmp = self.cmp_fn(t)?;
        let pv = self.val(t)?.unwrap_or(Val::I32);
        let t = t.clone();
        self.rt_fn(&format!("bisect_{}:{:?}", if left { "left" } else { "right" }, t), |w| {
            let (lt, arr) = (w.t.list[k as usize], w.t.arr[k as usize]);
            w.fx.params = vec![Val::Ref(Heap::Idx(lt)), pv];
            let (lo, hi, mid) = (w.fx.local(Val::I32), w.fx.local(Val::I32), w.fx.local(Val::I32));
            w.c().local_get(0).struct_get(lt, 1).local_set(hi);
            w.c().block(Block::Empty).loop_(Block::Empty);
            w.c().local_get(lo).local_get(hi).i32_ge_s().br_if(1);
            w.c().local_get(lo).local_get(hi).i32_add().i32_const(1).i32_shr_u().local_set(mid);
            // left: a[mid] < x → lo = mid + 1; right: x < a[mid] → hi = mid
            if left {
                w.c().local_get(0).struct_get(lt, 0).local_get(mid).array_get(arr);
                w.cast_item(&t)?;
                w.c().local_get(1).call(cmp).i32_const(0).i32_lt_s();
            } else {
                w.c().local_get(1).local_get(0).struct_get(lt, 0).local_get(mid).array_get(arr);
                w.cast_item(&t)?;
                w.c().call(cmp).i32_const(0).i32_ge_s();
            }
            w.c().if_(Block::Empty).local_get(mid).i32_const(1).i32_add().local_set(lo).else_().local_get(mid).local_set(hi).end();
            w.c().br(0);
            w.c().end().end().local_get(lo).i64_extend_i32_s();
            Ok(vec![Val::I64])
        })
    }

    /// heapq's functions on a list of `t`.
    fn heap_fn(&mut self, name: &str, a: &[Expr]) -> Res<()> {
        let Ty::List(t) = &a[0].ty else { return unsupported(name) };
        let t = t.as_ref().clone();
        let k = self.kind(&t)?;
        let (lt, arr) = (self.t.list[k as usize], self.t.arr[k as usize]);
        let (down, up) = (self.rt_siftdown(&t)?, self.rt_siftup(&t)?);
        let l = self.fx.local(Val::Ref(Heap::Idx(lt)));
        let kv = self.kval_of(k);
        let (x, r) = (self.fx.local(kv), self.fx.local(kv));
        self.expr(&a[0])?;
        self.c().local_set(l);
        if let Some(item) = a.get(1) {
            self.expr(item)?;
            self.c().local_set(x);
        }
        let empty = |w: &mut W| -> Res<()> {
            w.c().local_get(l).struct_get(lt, 1).i32_eqz().if_(Block::Empty);
            w.labeled(Lab::Plain, |w| w.raise_msg("IndexError", "index out of range"))?;
            w.c().end();
            Ok(())
        };
        match name {
            "heapq.heappush" => {
                let app = self.rt_list_append(k)?;
                self.c().local_get(l).local_get(x).call(app);
                self.c().local_get(l).i32_const(0).local_get(l).struct_get(lt, 1).i32_const(1).i32_sub().call(down);
            }
            "heapq.heappop" => {
                // lastelt = pop(); if heap: return heap[0] (heap[0] = lastelt, sift up)
                empty(self)?;
                let pop = self.rt_list_pop(k)?;
                self.c().local_get(l).i64_const(-1).i32_const(1).call(pop).local_set(x);
                self.c().local_get(x).local_set(r);
                self.c().local_get(l).struct_get(lt, 1).if_(Block::Empty);
                self.c().local_get(l).struct_get(lt, 0).i32_const(0).array_get(arr).local_set(r);
                self.c().local_get(l).struct_get(lt, 0).i32_const(0).local_get(x).array_set(arr);
                self.c().local_get(l).i32_const(0).call(up).end();
                self.c().local_get(r);
                self.cast_item(&t)?;
            }
            "heapq.heapify" => {
                let i = self.fx.local(Val::I32);
                self.c().local_get(l).struct_get(lt, 1).i32_const(2).i32_div_s().local_set(i);
                self.c().block(Block::Empty).loop_(Block::Empty);
                self.c().local_get(i).i32_eqz().br_if(1);
                self.c().local_get(i).i32_const(1).i32_sub().local_set(i);
                self.c().local_get(l).local_get(i).call(up).br(0);
                self.c().end().end();
            }
            "heapq.heapreplace" => {
                empty(self)?;
                self.c().local_get(l).struct_get(lt, 0).i32_const(0).array_get(arr).local_set(r);
                self.c().local_get(l).struct_get(lt, 0).i32_const(0).local_get(x).array_set(arr);
                self.c().local_get(l).i32_const(0).call(up).local_get(r);
                self.cast_item(&t)?;
            }
            _ => {
                // heappushpop: if heap and heap[0] < item: swap them and sift up
                let cmp = self.cmp_fn(&t)?;
                self.c().local_get(x).local_set(r);
                self.c().local_get(l).struct_get(lt, 1).if_(Block::Empty);
                self.c().local_get(l).struct_get(lt, 0).i32_const(0).array_get(arr);
                self.cast_item(&t)?;
                self.c().local_get(x);
                self.cast_item(&t)?;
                self.c().call(cmp).i32_const(0).i32_lt_s().if_(Block::Empty);
                self.c().local_get(l).struct_get(lt, 0).i32_const(0).array_get(arr).local_set(r);
                self.c().local_get(l).struct_get(lt, 0).i32_const(0).local_get(x).array_set(arr);
                self.c().local_get(l).i32_const(0).call(up).end().end();
                self.c().local_get(r);
                self.cast_item(&t)?;
            }
        }
        Ok(())
    }

    /// A list item as stored (its kind's value) → a value of `t`.
    fn cast_item(&mut self, t: &Ty) -> Res<()> {
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

    /// CPython's `_siftdown(heap, startpos, pos)`.
    fn rt_siftdown(&mut self, t: &Ty) -> Res<u32> {
        let k = self.kind(t)?;
        let cmp = self.cmp_fn(t)?;
        let t = t.clone();
        self.rt_fn(&format!("siftdown:{:?}", t), |w| {
            let (lt, arr) = (w.t.list[k as usize], w.t.arr[k as usize]);
            let kv = w.kval_of(k);
            w.fx.params = vec![Val::Ref(Heap::Idx(lt)), Val::I32, Val::I32];
            let (item, parent, pp) = (w.fx.local(kv), w.fx.local(kv), w.fx.local(Val::I32));
            w.c().local_get(0).struct_get(lt, 0).local_get(2).array_get(arr).local_set(item);
            w.c().block(Block::Empty).loop_(Block::Empty);
            w.c().local_get(2).local_get(1).i32_le_s().br_if(1);
            w.c().local_get(2).i32_const(1).i32_sub().i32_const(1).i32_shr_s().local_set(pp);
            w.c().local_get(0).struct_get(lt, 0).local_get(pp).array_get(arr).local_set(parent);
            w.c().local_get(item);
            w.cast_item(&t)?;
            w.c().local_get(parent);
            w.cast_item(&t)?;
            w.c().call(cmp).i32_const(0).i32_ge_s().br_if(1);
            w.c().local_get(0).struct_get(lt, 0).local_get(2).local_get(parent).array_set(arr);
            w.c().local_get(pp).local_set(2).br(0);
            w.c().end().end();
            w.c().local_get(0).struct_get(lt, 0).local_get(2).local_get(item).array_set(arr);
            Ok(vec![])
        })
    }

    /// CPython's `_siftup(heap, pos)`.
    fn rt_siftup(&mut self, t: &Ty) -> Res<u32> {
        let k = self.kind(t)?;
        let cmp = self.cmp_fn(t)?;
        let down = self.rt_siftdown(t)?;
        let t = t.clone();
        self.rt_fn(&format!("siftup:{:?}", t), |w| {
            let (lt, arr) = (w.t.list[k as usize], w.t.arr[k as usize]);
            let kv = w.kval_of(k);
            w.fx.params = vec![Val::Ref(Heap::Idx(lt)), Val::I32];
            let (item, end, start, child, right) = (w.fx.local(kv), w.fx.local(Val::I32), w.fx.local(Val::I32), w.fx.local(Val::I32), w.fx.local(Val::I32));
            w.c().local_get(0).struct_get(lt, 1).local_set(end).local_get(1).local_set(start);
            w.c().local_get(0).struct_get(lt, 0).local_get(1).array_get(arr).local_set(item);
            w.c().local_get(1).i32_const(1).i32_shl().i32_const(1).i32_add().local_set(child);
            w.c().block(Block::Empty).loop_(Block::Empty);
            w.c().local_get(child).local_get(end).i32_ge_s().br_if(1);
            // the smaller child (the right one unless the left is smaller)
            w.c().local_get(child).i32_const(1).i32_add().local_tee(right).local_get(end).i32_lt_s().if_(Block::Empty);
            w.c().local_get(0).struct_get(lt, 0).local_get(child).array_get(arr);
            w.cast_item(&t)?;
            w.c().local_get(0).struct_get(lt, 0).local_get(right).array_get(arr);
            w.cast_item(&t)?;
            w.c().call(cmp).i32_const(0).i32_ge_s().if_(Block::Empty).local_get(right).local_set(child).end();
            w.c().end();
            w.c().local_get(0).struct_get(lt, 0).local_get(1).local_get(0).struct_get(lt, 0).local_get(child).array_get(arr).array_set(arr);
            w.c().local_get(child).local_set(1);
            w.c().local_get(1).i32_const(1).i32_shl().i32_const(1).i32_add().local_set(child).br(0);
            w.c().end().end();
            w.c().local_get(0).struct_get(lt, 0).local_get(1).local_get(item).array_set(arr);
            w.c().local_get(0).local_get(start).local_get(1).call(down);
            Ok(vec![])
        })
    }
}
