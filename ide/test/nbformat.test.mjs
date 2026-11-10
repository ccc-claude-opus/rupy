// node --test ide/test (after sh ide/build.sh): notebooks with the real compiler
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseNotebook, serializeNotebook, buildProgram, locate, outputSplitter, newCell } from "../public/nbformat.mjs";
import { run } from "../public/rupy/rupy_wasm.mjs";

const compiler = (await WebAssembly.instantiate(readFileSync(new URL("../public/rupy/rupy.wasm", import.meta.url)), {})).instance.exports;

function compile(text) {
  const bytes = new TextEncoder().encode(text);
  const p = compiler.alloc(bytes.length);
  new Uint8Array(compiler.memory.buffer, p, bytes.length).set(bytes);
  const status = compiler.compile(p, bytes.length);
  const out = new Uint8Array(compiler.memory.buffer, compiler.out_ptr(), compiler.out_len()).slice();
  return status === 0 ? { wasm: out } : { error: new TextDecoder().decode(out) };
}

async function runCells(cells, upto) {
  const { src, starts } = buildProgram(cells, upto);
  const r = compile(src);
  if (r.error) return { error: r.error, starts };
  const outs = {};
  const split = outputSplitter((cell, text) => (outs[cell] = (outs[cell] ?? "") + text));
  let stderr = "";
  const code = await run(r.wasm, { stdout: split.feed, stderr: (s) => (stderr += s) });
  return { outs, stderr, code, last: split.current };
}

const cells = [
  newCell("markdown", "# Title\n$x^2$"),
  newCell("code", "x: int = 3\nprint(x)\n"),
  newCell("code", "def sq(n: int) -> int:\n    return n * n\n"),
  newCell("code", "print(sq(x))\nprint('done')"),
];

test("cells run as one program and their output is split", async () => {
  const r = await runCells(cells, 3);
  assert.equal(r.code, 0);
  assert.deepEqual(r.outs, { 1: "3\n", 2: "", 3: "9\ndone\n" });
});

test("running a cell runs only the cells above it", async () => {
  const r = await runCells(cells, 1);
  assert.deepEqual(r.outs, { 1: "3\n" });
});

test("a compile error is located in its cell", () => {
  const bad = [...cells, newCell("code", "y = 1\nx = 'a'\n")];
  const { src, starts } = buildProgram(bad);
  const r = compile(src);
  const line = +r.error.match(/line (\d+)/)[1];
  assert.deepEqual(locate(starts, line), { cell: 4, line: 2 });
});

test("a runtime error belongs to the cell that printed last", async () => {
  const r = await runCells([newCell("code", "print(1)"), newCell("code", "xs = [1]\nprint(xs[3])")]);
  assert.equal(r.code, 1);
  assert.equal(r.last, 1);
  assert.match(r.stderr, /IndexError/);
});

test(".ipynb round trip", () => {
  const nb = { cells: [{ ...cells[1], outputs: [{ name: "stdout", text: "3\n" }], count: 1 }, cells[0]], metadata: {} };
  const back = parseNotebook(serializeNotebook(nb));
  assert.deepEqual(back.cells, nb.cells.map((c) => ({ ...c, source: c.source })));
  const j = JSON.parse(serializeNotebook(nb));
  assert.equal(j.nbformat, 4);
  assert.deepEqual(j.cells[0].source, ["x: int = 3\n", "print(x)\n"]);
});

test("Jupyter outputs and an empty file", () => {
  const nb = parseNotebook(JSON.stringify({ cells: [{ cell_type: "code", source: "1", execution_count: 2, outputs: [{ output_type: "execute_result", data: { "text/plain": ["1"] } }, { output_type: "error", ename: "E", evalue: "v", traceback: ["t"] }] }] }));
  assert.deepEqual(nb.cells[0].outputs, [{ name: "stdout", text: "1" }, { name: "stderr", text: "t\n" }]);
  assert.equal(parseNotebook("").cells.length, 1);
});

test("output over several chunks keeps its cell", () => {
  const outs = {};
  const s = outputSplitter((c, t) => (outs[c] = (outs[c] ?? "") + t));
  s.feed("\x1e1\x1ea\n");
  s.feed("b\n\x1e2\x1e");
  s.feed("c");
  assert.deepEqual(outs, { 1: "a\nb\n", 2: "c" });
});
