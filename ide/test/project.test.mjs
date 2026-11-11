// node --test ide/test (after sh ide/build.sh): programs of several files, as the IDE compiles them
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { run } from "../public/rupy/rupy_wasm.mjs";

const compiler = (await WebAssembly.instantiate(readFileSync(new URL("../public/rupy/rupy.wasm", import.meta.url)), {})).instance.exports;

function compile(project) {
  const bytes = new TextEncoder().encode(typeof project === "string" ? project : JSON.stringify(project));
  const p = compiler.alloc(bytes.length);
  new Uint8Array(compiler.memory.buffer, p, bytes.length).set(bytes);
  const status = compiler.compile_project(p, bytes.length);
  const out = new Uint8Array(compiler.memory.buffer, compiler.out_ptr(), compiler.out_len()).slice();
  return status === 0 ? { wasm: out } : { error: JSON.parse(new TextDecoder().decode(out)) };
}

async function output(project) {
  const r = compile(project);
  if (r.error) return r;
  let out = "";
  await run(r.wasm, { stdout: (s) => (out += s) });
  return { out };
}

const geometry = `from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float


def dist(a: Point, b: Point) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
`;

test("a program imports a module of the workspace", async () => {
  const files = { "main.py": "from geometry import Point, dist\nimport util\nprint(dist(Point(0.0, 0.0), Point(3.0, 4.0)), util.twice(2))\n", "geometry.py": geometry, "util.py": "def twice(n: int) -> int:\n    return 2 * n\n", "other.py": "this is not python" };
  assert.deepEqual(await output({ main: "main.py", files }), { out: "5.0 4\n" });
});

test("modules are found next to the main file", async () => {
  const files = { "lib/main.py": "import helper\nprint(helper.f())\n", "lib/helper.py": "def f() -> str:\n    return 'lib'\n" };
  assert.deepEqual(await output({ main: "lib/main.py", files }), { out: "lib\n" });
});

test("an error is reported in its file", () => {
  const files = { "main.py": "import util\nprint(util.twice(2))\n", "util.py": "def twice(n: int) -> int:\n    return 'x'\n" };
  const { error } = compile({ main: "main.py", files });
  assert.equal(error.file, "util.py");
  assert.equal(error.line, 2);
  assert.match(error.msg, /str|int/);
});

test("errors of the main file, a missing main, bad JSON", () => {
  assert.deepEqual(Object.keys(compile({ main: "a.py", files: { "a.py": "x: int = 1\nx = 'a'\n" } }).error), ["file", "hint", "line", "msg"]);
  assert.equal(compile({ main: "a.py", files: { "a.py": "x: int = 1\nx = 'a'\n" } }).error.line, 2);
  assert.match(compile({ main: "nope.py", files: {} }).error.msg, /no file/);
  assert.match(compile("{").error.msg, /bad project JSON/);
});

test("a module with top-level statements is rejected", () => {
  const { error } = compile({ main: "m.py", files: { "m.py": "import u\n", "u.py": "print(1)\n" } });
  assert.equal(error.file, "u.py");
  assert.match(error.msg, /may only define/);
});

test("random, itertools and re run in the browser, as in CPython", async () => {
  const main = `import random
import re
from itertools import combinations

random.seed(7)
print(random.randint(1, 100), random.choice(["a", "b", "c"]))
print(list(combinations("abc", 2)))
m = re.search(r"(\\w+)@(\\w+)", "mail: ann@example")
if m is not None:
    print(m.group(1), m.span(2))
print(re.sub(r"\\d", "#", "a1b22"))
`;
  const r = await output({ main: "main.py", files: { "main.py": main } });
  assert.equal(r.error, undefined);
  assert.equal(r.out, "42 a\n[('a', 'b'), ('a', 'c'), ('b', 'c')]\nann (10, 17)\na#b##\n");
});

test("a generator runs one item at a time", async () => {
  const main = `from typing import Iterator


def count(n: int) -> Iterator[int]:
    for i in range(n):
        print("make", i)
        yield i


for x in count(2):
    print("got", x)
`;
  const r = await output({ main: "main.py", files: { "main.py": main } });
  assert.equal(r.error, undefined);
  assert.equal(r.out, "make 0\ngot 0\nmake 1\ngot 1\n");
});
