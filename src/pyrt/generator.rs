//! Generators: the body runs on its own thread, strictly in turn with the
//! consumer (it starts on the first `next` and stops at each `yield` until the
//! next one), so output interleaves exactly as in CPython. Each `next` passes
//! on whether the consumer catches exceptions; an exception raised in the body
//! then comes back to the consumer's `next`, and the generator is finished.

use std::sync::mpsc::{sync_channel, Receiver, SyncSender};

/// The unwinding that ends a generator whose consumer is gone.
struct Closed;

/// What the body sends back: a value, its end, or an exception for the consumer.
enum Msg<T> {
    Val(T),
    Done,
    Raised(Box<dyn std::any::Any + Send>),
}

/// The generator side: `y.yield_(v)`.
pub struct Yield<T> {
    /// each request carries the consumer's catching depth
    req: Receiver<u32>,
    val: SyncSender<Msg<T>>,
}

impl<T> Yield<T> {
    pub fn yield_(&self, v: T) {
        if self.val.send(Msg::Val(v)).is_err() {
            std::panic::resume_unwind(Box::new(Closed));
        }
        match self.req.recv() {
            Ok(depth) => crate::pyrt::err::set_catching(depth),
            Err(_) => std::panic::resume_unwind(Box::new(Closed)),
        }
    }
}

/// A generator object (an iterator).
pub struct Gen<T> {
    req: Option<SyncSender<u32>>,
    val: Receiver<Msg<T>>,
}

impl<T: Send + 'static> Gen<T> {
    pub fn new(body: impl FnOnce(&Yield<T>) + Send + 'static) -> Gen<T> {
        let (req_tx, req_rx) = sync_channel::<u32>(0);
        let (val_tx, val_rx) = sync_channel::<Msg<T>>(0);
        std::thread::Builder::new()
            .stack_size(64 << 20)
            .spawn(move || {
                let Ok(depth) = req_rx.recv() else { return };
                crate::pyrt::err::set_catching(depth);
                let y = Yield { req: req_rx, val: val_tx };
                let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| body(&y)));
                match r {
                    Ok(()) => {
                        let _ = y.val.send(Msg::Done);
                    }
                    Err(e) if e.is::<Closed>() => {}
                    // raised while the consumer catches: its `next` raises it
                    Err(e) => {
                        let _ = y.val.send(Msg::Raised(e));
                    }
                }
            })
            .expect("generator thread");
        Gen { req: Some(req_tx), val: val_rx }
    }
}

impl<T> Iterator for Gen<T> {
    type Item = T;
    fn next(&mut self) -> Option<T> {
        let req = self.req.as_ref()?;
        if req.send(crate::pyrt::err::catching_depth()).is_err() {
            self.req = None;
            return None;
        }
        match self.val.recv() {
            Ok(Msg::Val(v)) => Some(v),
            Ok(Msg::Raised(e)) => {
                self.req = None;
                std::panic::resume_unwind(e)
            }
            _ => {
                self.req = None;
                None
            }
        }
    }
}

/// `next(g)`
pub fn next<T>(g: &mut Gen<T>) -> T {
    g.next().unwrap_or_else(|| crate::pyrt::raise("StopIteration", ""))
}

/// `for x in g` where the loop's try catches what the body raises: each item,
/// or the exception the generator raised.
pub struct CatchingIter<T> {
    g: Gen<T>,
}

pub fn catching_iter<T>(g: Gen<T>) -> CatchingIter<T> {
    CatchingIter { g }
}

impl<T> Iterator for CatchingIter<T> {
    type Item = crate::pyrt::err::PyResult<T>;
    fn next(&mut self) -> Option<Self::Item> {
        match crate::pyrt::err::catching(|| self.g.next()) {
            Ok(Some(v)) => Some(Ok(v)),
            Ok(None) => None,
            Err(e) => Some(Err(e)),
        }
    }
}
