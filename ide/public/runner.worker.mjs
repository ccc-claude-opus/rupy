// A Web Worker that compiles rupy with rupy.wasm and runs the result with the
// host rupy_wasm.mjs, so a long or endless program never blocks the page: the
// page stops it by terminating the worker (runner.mjs).
//
// in:  { id, op: "compile" | "run", src, stdin }
// out: { id, type: "ready" } once, then for a request
//      { id, type: "out", fd, text } … and { id, type: "done", error?, code?, bytes, compileMs, runMs }
import { run } from "./rupy/rupy_wasm.mjs";

const compiler = (await WebAssembly.instantiateStreaming(fetch("./rupy/rupy.wasm"), {})).instance.exports;

function compile(text) {
  const bytes = new TextEncoder().encode(text);
  const p = compiler.alloc(bytes.length);
  new Uint8Array(compiler.memory.buffer, p, bytes.length).set(bytes);
  const status = compiler.compile(p, bytes.length);
  const out = new Uint8Array(compiler.memory.buffer, compiler.out_ptr(), compiler.out_len()).slice();
  return status === 0 ? { wasm: out } : { error: new TextDecoder().decode(out) };
}

// output is sent in batches: at most every 50 ms or 16 KB (a program runs
// synchronously, so a timer would not fire until it ends)
function writer(id, fd) {
  let buf = "";
  let last = performance.now();
  const flush = () => {
    if (buf) postMessage({ id, type: "out", fd, text: buf });
    buf = "";
    last = performance.now();
  };
  const write = (s) => {
    buf += s;
    if (buf.length > 16384 || performance.now() - last > 50) flush();
  };
  return { write, flush };
}

onmessage = async ({ data: { id, op, src, stdin } }) => {
  const t0 = performance.now();
  let r;
  try {
    r = compile(src);
  } catch (e) {
    r = { error: "the compiler failed: " + e };
  }
  const t1 = performance.now();
  if (r.error || op === "compile") {
    postMessage({ id, type: "done", error: r.error ?? null, bytes: r.wasm?.length ?? 0, compileMs: t1 - t0 });
    return;
  }
  const out = writer(id, 1), err = writer(id, 2);
  let code;
  try {
    code = await run(r.wasm, { stdout: out.write, stderr: err.write, stdin: stdin ?? "" });
  } catch (e) {
    err.write(`\n${e?.stack ?? e}\n`);
    code = 1;
  }
  out.flush();
  err.flush();
  postMessage({ id, type: "done", code, bytes: r.wasm.length, compileMs: t1 - t0, runMs: performance.now() - t1 });
};

postMessage({ type: "ready" });
