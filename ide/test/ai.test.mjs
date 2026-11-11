// node --test ide/test: the AI assistant's API on a real rucloud (skipped without
// `rucloud` on PATH), in front of a fake OpenAI-compatible server
import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { cpSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const hasRucloud = spawnSync("rucloud", ["--version"]).status === 0;
const ide = fileURLToPath(new URL("..", import.meta.url));
const PORT = 19000 + Math.floor(Math.random() * 1000);
const base = `http://127.0.0.1:${PORT}`;
let server, llm, dir, state;
const seen = []; // the requests the fake LLM got

before(async () => {
  if (!hasRucloud) return;
  // the fake LLM: thinks, then answers in three pieces
  llm = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen.push({ url: req.url, auth: req.headers.authorization, body: JSON.parse(body) });
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      const chunk = (delta) => res.write(`data: ${JSON.stringify({ choices: [{ delta }] })}\n\n`);
      chunk({ reasoning_content: "hmm" });
      for (const s of ["改好了：\n```python\n", "print(1)\n", "```\n"]) chunk({ content: s });
      res.end("data: [DONE]\n\n");
    });
  });
  await new Promise((r) => llm.listen(0, "127.0.0.1", r));
  // a copy of the app with its own .dev.vars
  dir = mkdtempSync(join(tmpdir(), "rupy-ide-ai-"));
  state = join(dir, ".state");
  for (const f of ["wrangler.jsonc", "src", "public"]) cpSync(join(ide, f), join(dir, f), { recursive: true, filter: (p) => !p.includes("/public/rupy") });
  writeFileSync(join(dir, ".dev.vars"), `AUTH_SECRET=test-secret\nAI_BASE_URL=http://127.0.0.1:${llm.address().port}/v1\nAI_MODEL=fake-model\nAI_API_KEY=k123\nAI_DAILY_LIMIT=2\n`);
  server = spawn("rucloud", ["dev", dir, "--port", String(PORT), "--state", state, "--no-watch"], { stdio: "ignore" });
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(base + "/api/health")).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("rucloud did not start");
});

after(() => {
  server?.kill();
  llm?.close();
  if (dir) rmSync(dir, { recursive: true, force: true });
});

const opts = { skip: !hasRucloud && "rucloud is not installed" };

async function signUp() {
  const res = await fetch(base + "/api/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: `a${Date.now()}@example.com`, password: "password123" }) });
  return res.headers.get("set-cookie").split(";")[0];
}

const chat = (cookie, body) =>
  fetch(base + "/api/ai/chat", { method: "POST", headers: { "Content-Type": "application/json", ...(cookie && { Cookie: cookie }) }, body: JSON.stringify(body) });

/** The events of a reply: [{ d } | { r } | { e }]. */
async function events(res) {
  const text = await res.text();
  return text
    .split("\n\n")
    .map((l) => l.replace(/^data: /, ""))
    .filter((l) => l && l !== "[DONE]")
    .map((l) => JSON.parse(l));
}

test("the AI assistant streams the model's reply, with the file and the error as context", opts, async () => {
  assert.equal((await chat(null, { messages: [{ role: "user", content: "hi" }] })).status, 401);
  const cookie = await signUp();
  const me = await (await fetch(base + "/api/me", { headers: { Cookie: cookie } })).json();
  assert.equal(me.ai, true);

  const res = await chat(cookie, {
    messages: [{ role: "user", content: "修正這個錯誤" }],
    context: { path: "main.py", text: "def f(x):\n    return x\n", error: "main.py 第 1 行：missing type", files: ["util.py"] },
  });
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-type"), /event-stream/);
  const ev = await events(res);
  assert.deepEqual(ev, [{ r: "hmm" }, { d: "改好了：\n```python\n" }, { d: "print(1)\n" }, { d: "```\n" }]);

  const got = seen[seen.length - 1];
  assert.equal(got.url, "/v1/chat/completions");
  assert.equal(got.auth, "Bearer k123"); // the key stays on the server
  assert.equal(got.body.model, "fake-model");
  assert.equal(got.body.stream, true);
  const [system, user] = got.body.messages;
  assert.equal(system.role, "system");
  assert.match(system.content, /rupy/);
  assert.match(system.content, /def f\(x\)/);
  assert.match(system.content, /missing type/);
  assert.match(system.content, /util\.py/);
  assert.deepEqual(user, { role: "user", content: "修正這個錯誤" });
});

test("bad requests, and the daily limit", opts, async () => {
  const cookie = await signUp();
  assert.equal((await chat(cookie, { messages: [] })).status, 400);
  assert.equal((await chat(cookie, { messages: [{ role: "assistant", content: "x" }] })).status, 400);
  assert.equal((await chat(cookie, { messages: [{ role: "user", content: "x".repeat(200_000) }] })).status, 413);
  // AI_DAILY_LIMIT=2
  for (let i = 0; i < 2; i++) assert.equal((await chat(cookie, { messages: [{ role: "user", content: "q" }] })).status, 200);
  const over = await chat(cookie, { messages: [{ role: "user", content: "q" }] });
  assert.equal(over.status, 429);
  assert.match((await over.json()).error, /額度/);
  // another site cannot use it
  const csrf = await fetch(base + "/api/ai/chat", { method: "POST", headers: { Cookie: cookie, Origin: "https://evil.example", "Content-Type": "application/json" }, body: "{}" });
  assert.equal(csrf.status, 403);
});

test("the code of a reply, and a model's thinking", async () => {
  const { extractCode, splitThinking } = await import("../public/ai.mjs");
  assert.equal(extractCode("no code"), null);
  assert.equal(extractCode("a\n```python\nx = 1\n```\nb\n```py\ny = 2\n\n```\n"), "y = 2\n");
  assert.equal(extractCode("```\nprint(1)\n```"), "print(1)\n");
  assert.equal(extractCode("```text\nnot python\n```"), null);
  assert.deepEqual(splitThinking("<think>hmm\n</think>\n\nanswer"), { thinking: "hmm", answer: "answer" });
  assert.deepEqual(splitThinking("<think>still thinking"), { thinking: "still thinking", answer: "" });
  assert.deepEqual(splitThinking("plain"), { thinking: "", answer: "plain" });
});
