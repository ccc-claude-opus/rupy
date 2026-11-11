// A Web Worker that compiles rupy with rupy.wasm and runs the result with the
// host rupy_wasm.mjs, so a long or endless program never blocks the page: the
// page stops it by terminating the worker (runner.mjs).
//
// in:  { id, op: "compile" | "run", project: { main, files: { path: text } }, stdin }
// out: { id, type: "ready" } once, then for a request
//      { id, type: "out", fd, text } …, { id, type: "file", path, text } for each file the
//      program wrote or removed (text null; open() reads and writes project.files), and
//      { id, type: "done", error?, code?, bytes, compileMs, runMs }
//      (error: { file, line, msg, hint }, line 0 when it has none)
import { run } from "./rupy/rupy_wasm.mjs";

const compiler = (await WebAssembly.instantiateStreaming(fetch("./rupy/rupy.wasm"), {})).instance.exports;

function compile(project) {
  const bytes = new TextEncoder().encode(JSON.stringify(project));
  const p = compiler.alloc(bytes.length);
  new Uint8Array(compiler.memory.buffer, p, bytes.length).set(bytes);
  const status = compiler.compile_project(p, bytes.length);
  const out = new Uint8Array(compiler.memory.buffer, compiler.out_ptr(), compiler.out_len()).slice();
  return status === 0 ? { wasm: out } : { error: JSON.parse(new TextDecoder().decode(out)) };
}

// The first 32 writes of every 50 ms are sent at once (so what a program printed
// before it hangs is seen, and stopping it loses nothing); more are batched until
// the next write after the 50 ms or 16 KB (a program runs synchronously, so a
// timer would not fire until it ends).
function writer(id, fd) {
  let buf = "";
  let since = 0, sent = 0;
  const flush = () => {
    if (buf) postMessage({ id, type: "out", fd, text: buf });
    buf = "";
  };
  const write = (s) => {
    buf += s;
    const now = performance.now();
    if (now - since > 50) {
      since = now;
      sent = 0;
    }
    if (sent < 32 || buf.length > 16384 || now === since) {
      sent++;
      flush();
    }
  };
  return { write, flush };
}

onmessage = async ({ data: { id, op, project, stdin } }) => {
  const t0 = performance.now();
  let r;
  try {
    r = compile(project);
  } catch (e) {
    r = { error: { file: project.main, line: 0, msg: "the compiler failed: " + e, hint: null } };
  }
  const t1 = performance.now();
  if (r.error || op === "compile") {
    postMessage({ id, type: "done", error: r.error ?? null, bytes: r.wasm?.length ?? 0, compileMs: t1 - t0 });
    return;
  }
  const out = writer(id, 1), err = writer(id, 2);
  let code;
  try {
    code = await run(r.wasm, {
      stdout: out.write,
      stderr: err.write,
      stdin: stdin ?? "",
      files: new Map(Object.entries(project.files)),
      onFile: (path, text) => {
        out.flush();
        err.flush();
        postMessage({ id, type: "file", path, text });
      },
    });
  } catch (e) {
    err.write(`\n${e?.stack ?? e}\n`);
    code = 1;
  }
  out.flush();
  err.flush();
  postMessage({ id, type: "done", code, bytes: r.wasm.length, compileMs: t1 - t0, runMs: performance.now() - t1 });
};

postMessage({ type: "ready" });
