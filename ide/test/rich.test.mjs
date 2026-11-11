// node --test ide/test: pictures in a program's output, files a program reads and writes
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { richSplitter } from "../public/rich.mjs";
import { parseNotebook, serializeNotebook, newCell } from "../public/nbformat.mjs";
import { run } from "../public/rupy/rupy_wasm.mjs";

/** Feed `chunks` to a richSplitter: the pieces it emits, text joined. */
function split(chunks) {
  const out = [];
  const r = richSplitter((kind, s) => {
    const last = out[out.length - 1];
    if (kind === "text" && last?.[0] === "text") last[1] += s;
    else out.push([kind, s]);
  });
  for (const c of chunks) r.feed(c);
  r.flush();
  return out;
}

const SVG = '<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="10pt" height="10pt">\n<rect/>\n</svg>';

test("an SVG document printed is a picture, wherever the chunks break", () => {
  const text = "before\n" + SVG + "\n\nafter <svg> in a line\n\n" + SVG + "\n\n\nend";
  const want = [["text", "before\n"], ["svg", SVG], ["text", "after <svg> in a line\n\n"], ["svg", SVG], ["text", "\nend"]];
  assert.deepEqual(split([text]), want);
  for (let n = 1; n < text.length; n += 7) {
    const chunks = [];
    for (let i = 0; i < text.length; i += n) chunks.push(text.slice(i, i + n));
    assert.deepEqual(split(chunks), want, `chunks of ${n}`);
  }
});

test("XML that is not SVG, an unfinished SVG, and a lone < stay text", () => {
  assert.deepEqual(split(['<?xml version="1.0"?>\n<a/>\n']), [["text", '<?xml version="1.0"?>\n<a/>\n']]);
  assert.deepEqual(split(["<svg width='1'>\n<rect/>"]), [["text", "<svg width='1'>\n<rect/>"]]);
  assert.deepEqual(split(["<", " 3\n"]), [["text", "< 3\n"]]);
  assert.deepEqual(split(["<"]), [["text", "<"]]);
});

test("a notebook keeps its pictures (nbformat display_data)", () => {
  const cell = newCell("code", "print(g.svg())");
  cell.outputs = [{ name: "stdout", text: "x\n" }, { name: "svg", text: SVG }];
  const text = serializeNotebook({ cells: [cell] });
  const out = JSON.parse(text).cells[0].outputs[1];
  assert.equal(out.output_type, "display_data");
  assert.equal(out.data["image/svg+xml"].join(""), SVG);
  assert.deepEqual(parseNotebook(text).cells[0].outputs, cell.outputs);
  // a PNG from Jupyter
  const png = { cells: [{ cell_type: "code", source: [], outputs: [{ output_type: "execute_result", data: { "image/png": "iVBORw0K\n", "text/plain": ["<Figure>"] } }] }] };
  assert.deepEqual(parseNotebook(JSON.stringify(png)).cells[0].outputs, [{ name: "png", text: "iVBORw0K\n" }]);
});

const compiler = (await WebAssembly.instantiate(readFileSync(new URL("../public/rupy/rupy.wasm", import.meta.url)), {})).instance.exports;

async function runProject(files, main = "main.py") {
  const bytes = new TextEncoder().encode(JSON.stringify({ main, files }));
  const p = compiler.alloc(bytes.length);
  new Uint8Array(compiler.memory.buffer, p, bytes.length).set(bytes);
  const status = compiler.compile_project(p, bytes.length);
  const out = new Uint8Array(compiler.memory.buffer, compiler.out_ptr(), compiler.out_len()).slice();
  assert.equal(status, 0, new TextDecoder().decode(out));
  let stdout = "";
  const written = {};
  const code = await run(out, { stdout: (s) => (stdout += s), stderr: (s) => (stdout += s), files: new Map(Object.entries(files)), onFile: (path, text) => (written[path] = text) });
  return { code, stdout, written };
}

test("a program reads the workspace's files and writes new ones", async () => {
  const main = `def total_of(path: str) -> int:
    total = 0
    with open(path) as f:
        for line in f:
            total += int(line.split(",")[1])
    return total


total = total_of("data.csv")
with open("out/total.txt", "w") as f:
    f.write("total " + str(total) + "\\n")
try:
    open("nope.txt")
except FileNotFoundError as e:
    print(e)
print(total)
`;
  const r = await runProject({ "main.py": main, "data.csv": "a,1\nb,2\nc,39\n" });
  assert.equal(r.stdout, "[Errno 2] No such file or directory: 'nope.txt'\n42\n");
  assert.deepEqual(r.written, { "out/total.txt": "total 42\n" });
});

test("rstatistics draws in the browser: print(g.svg()) and g.save()", async () => {
  const main = `import rstatistics as r
g = r.Graphics(5.0, 4.0)
g.hist([1.0, 2.0, 2.5, 3.0, 3.5, 4.0, 6.0], main="h", xlab="x", ylab="n")
print(g.svg())
g.save("hist.svg")
`;
  const r = await runProject({ "main.py": main });
  assert.equal(r.code, 0, r.stdout);
  assert.match(r.stdout, /^<\?xml[^]*<svg[^]*<\/svg>\n\n$/);
  assert.equal(r.written["hist.svg"], r.stdout.slice(0, -1));
  const parts = split([r.stdout]);
  assert.deepEqual(parts.map((p) => p[0]), ["svg"]);
});
