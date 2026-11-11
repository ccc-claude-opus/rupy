// node --test ide/test: the API on a real rucloud (skipped without `rucloud` on PATH)
import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const hasRucloud = spawnSync("rucloud", ["--version"]).status === 0;
const ide = fileURLToPath(new URL("..", import.meta.url));
const PORT = 18000 + Math.floor(Math.random() * 1000);
const base = `http://127.0.0.1:${PORT}`;
let server, state, wroteVars = false;

before(async () => {
  if (!hasRucloud) return;
  state = mkdtempSync(join(tmpdir(), "rupy-ide-"));
  if (!existsSync(join(ide, ".dev.vars"))) {
    writeFileSync(join(ide, ".dev.vars"), "AUTH_SECRET=test-secret-for-api-tests\n");
    wroteVars = true;
  }
  server = spawn("rucloud", ["dev", ide, "--port", String(PORT), "--state", state], { stdio: "ignore" });
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
  if (state) rmSync(state, { recursive: true, force: true });
  if (wroteVars) rmSync(join(ide, ".dev.vars"));
});

// a client with its own cookie
function client() {
  let cookie = "";
  return async (path, { method = "GET", body, headers = {} } = {}) => {
    const res = await fetch(base + path, {
      method,
      headers: { ...(cookie && { Cookie: cookie }), ...(typeof body === "object" && { "Content-Type": "application/json" }), ...headers },
      body: typeof body === "object" ? JSON.stringify(body) : body,
    });
    const set = res.headers.get("set-cookie");
    if (set) cookie = set.split(";")[0];
    const type = res.headers.get("content-type") ?? "";
    return { status: res.status, headers: res.headers, data: type.includes("json") ? await res.json() : await res.text() };
  };
}

const opts = { skip: !hasRucloud && "rucloud is not installed" };
const email = `u${Date.now()}@example.com`;

test("accounts", opts, async () => {
  const a = client();
  const anon = (await a("/api/me")).data;
  assert.equal(anon.accounts, true);
  assert.equal(anon.user, null);
  assert.equal((await a("/api/files")).status, 401);
  assert.equal((await a("/api/register", { method: "POST", body: { email, password: "short" } })).status, 400);
  const r = await a("/api/register", { method: "POST", body: { email, password: "password123" } });
  assert.equal(r.status, 200);
  assert.equal((await a("/api/me")).data.user.email, email);
  assert.equal((await a("/api/register", { method: "POST", body: { email, password: "password123" } })).status, 400);
  const b = client();
  assert.equal((await b("/api/login", { method: "POST", body: { email, password: "wrong-pass" } })).status, 400);
  assert.equal((await b("/api/login", { method: "POST", body: { email, password: "password123" } })).status, 200);
  await b("/api/logout", { method: "POST" });
  assert.equal((await b("/api/me")).data.user, null);
  // another site cannot post
  assert.equal((await a("/api/logout", { method: "POST", headers: { Origin: "https://evil.example" } })).status, 403);
});

test("files and versions", opts, async () => {
  const a = client();
  await a("/api/login", { method: "POST", body: { email, password: "password123" } });
  assert.equal((await a("/api/files/x.py", { method: "PUT", body: "1" })).status, 428);
  assert.equal((await a("/api/files/..%2Fx.py", { method: "PUT", body: "1", headers: { "If-Match": "0" } })).status, 400);
  let r = await a("/api/files/dir/x.py", { method: "PUT", body: "print(1)\n", headers: { "If-Match": "0" } });
  assert.equal(r.data.version, 1);
  // a second new file of the same name, or an old base: 409 with the version
  r = await a("/api/files/dir/x.py", { method: "PUT", body: "print(2)\n", headers: { "If-Match": "0" } });
  assert.deepEqual([r.status, r.data.version], [409, 1]);
  r = await a("/api/files/dir/x.py", { method: "PUT", body: "print(2)\n", headers: { "If-Match": "1" } });
  assert.equal(r.data.version, 2);
  r = await a("/api/files/dir/x.py");
  assert.deepEqual([r.data, r.headers.get("x-version")], ["print(2)\n", "2"]);
  assert.deepEqual((await a("/api/files")).data.files.map((f) => [f.path, f.version, f.size]), [["dir/x.py", 2, 9]]);
  assert.equal((await a("/api/files/dir/x.py?version=1", { method: "DELETE" })).status, 409);
  assert.equal((await a("/api/files/dir/x.py?version=2", { method: "DELETE" })).status, 200);
  assert.equal((await a("/api/files/dir/x.py")).status, 404);
  // another account sees none of it
  const b = client();
  await b("/api/register", { method: "POST", body: { email: "b" + email, password: "password123" } });
  await a("/api/files/mine.py", { method: "PUT", body: "1", headers: { "If-Match": "0" } });
  assert.deepEqual((await b("/api/files")).data.files, []);
  assert.equal((await b("/api/files/mine.py")).status, 404);
});

test("share links", opts, async () => {
  const a = client();
  await a("/api/login", { method: "POST", body: { email, password: "password123" } });
  const r = await a("/api/shares", { method: "POST", body: { path: "nb.ipynb", text: "{}" } });
  assert.match(r.data.url, /^\/s\/[0-9a-f]{16}$/);
  const anon = client();
  const shared = (await anon("/api/s/" + r.data.id)).data;
  assert.deepEqual([shared.path, shared.text], ["nb.ipynb", "{}"]);
  assert.match((await anon(r.data.url)).data, /<html/);
  assert.equal((await a("/api/shares")).data.shares.length, 1);
  await a("/api/shares/" + r.data.id, { method: "DELETE" });
  assert.equal((await anon("/api/s/" + r.data.id)).status, 404);
});
