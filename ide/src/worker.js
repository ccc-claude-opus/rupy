// The rupy IDE's API. Programs compile and run in the browser; the server keeps
// accounts, each account's files and read-only share links.
//   /api/register, /api/login, /api/logout, /api/me   accounts (PBKDF2, HMAC-signed cookie)
//   /api/files[/<path>]                               the account's files (list, get, put, delete)
//   /api/shares[/<id>]                                share links of the account (create, list, delete)
//   /api/s/<id>                                       a shared file (public)
//   /api/ai/chat                                      the AI assistant (a stream of server-sent events)
//   /s/<id>                                           the share page (public/share.html)
// Files: a row in D1 (path, version, size, mtime, obj) and the text in R2 under
// obj = u/<user>/<random>, a new object for every write; a PUT names the version
// it is based on (If-Match) and gets 409 when the file changed in between. Shares are snapshots in R2 (s/<id>).
// AUTH_SECRET (.dev.vars) signs the cookie; without it there are no accounts.
// The AI assistant: AI_BASE_URL, AI_MODEL, AI_API_KEY (an OpenAI-compatible API),
// or else a Workers AI binding (env.AI); AI_DAILY_LIMIT requests a day per account.

const COOKIE = "rupy_session";
const SESSION_DAYS = 30;
const MAX_FILE = 1 << 20;
const MAX_FILES = 1000;
const enc = new TextEncoder();

const json = (obj, status = 200, headers = {}) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...headers } });

const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const unhex = (h) => new Uint8Array(h.match(/../g).map((b) => parseInt(b, 16)));
const randomHex = (bytes) => hex(crypto.getRandomValues(new Uint8Array(bytes)));
const now = () => new Date().toISOString();

class HttpError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

// ------------------------------------------------------------- accounts

async function hmacHex(data, secret) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}

async function hashPassword(password, saltHex) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  return hex(await crypto.subtle.deriveBits({ name: "PBKDF2", salt: unhex(saltHex), iterations: 100_000, hash: "SHA-256" }, key, 256));
}

function getCookie(request, name) {
  const m = (request.headers.get("Cookie") || "").match(new RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
  return m && decodeURIComponent(m[1]);
}

async function sessionCookie(userId, env) {
  const exp = Date.now() + SESSION_DAYS * 86400_000;
  const payload = `${userId}.${exp}`;
  return `${COOKIE}=${payload}.${await hmacHex(payload, env.AUTH_SECRET)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_DAYS * 86400}`;
}

async function currentUserId(request, env) {
  const token = getCookie(request, COOKIE);
  if (!token || !env.AUTH_SECRET) return null;
  const [id, exp, sig] = token.split(".");
  if (!id || !exp || !sig || Number(exp) < Date.now()) return null;
  if ((await hmacHex(`${id}.${exp}`, env.AUTH_SECRET)) !== sig) return null;
  return Number(id);
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    throw new HttpError(400, "格式不對");
  }
}

async function register(request, env, db) {
  const { email, password } = await readJson(request);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(email || ""))) throw new HttpError(400, "請輸入正確的 email");
  if (String(password || "").length < 8) throw new HttpError(400, "密碼至少 8 個字");
  const salt = randomHex(16);
  const hash = await hashPassword(String(password), salt);
  let result;
  try {
    result = await db.prepare("INSERT INTO users (email, pass_hash, pass_salt, created_at) VALUES (?, ?, ?, ?)").bind(String(email).toLowerCase(), hash, salt, now()).run();
  } catch {
    throw new HttpError(400, "這個 email 已經註冊過了");
  }
  const user = { id: result.meta.last_row_id, email: String(email).toLowerCase() };
  return json({ user }, 200, { "Set-Cookie": await sessionCookie(user.id, env) });
}

async function login(request, env, db) {
  const { email, password } = await readJson(request);
  const row = await db.prepare("SELECT * FROM users WHERE email = ?").bind(String(email || "").toLowerCase()).first();
  // hash anyway, so a wrong email takes as long as a wrong password
  const hash = await hashPassword(String(password || ""), row?.pass_salt ?? "00");
  if (!row || hash !== row.pass_hash) throw new HttpError(400, "email 或密碼不對");
  return json({ user: { id: row.id, email: row.email } }, 200, { "Set-Cookie": await sessionCookie(row.id, env) });
}

// ---------------------------------------------------------------- files

/** A file path from the URL: letters, digits, _ . - and /, no "..", at most 200 characters. */
function filePath(raw) {
  let p;
  try {
    p = decodeURIComponent(raw);
  } catch {
    throw new HttpError(400, "檔名不對");
  }
  if (!/^[\w.\-]+(\/[\w.\-]+)*$/.test(p) || p.length > 200 || p.split("/").some((s) => s === "." || s === "..")) throw new HttpError(400, "檔名只能用英數字、底線、點、減號和 /");
  return p;
}

const newObjectKey = (userId) => `u/${userId}/${randomHex(12)}`;

async function listFiles(db, userId) {
  const { results } = await db.prepare("SELECT path, version, size, mtime FROM files WHERE user_id = ? ORDER BY path").bind(userId).all();
  return json({ files: results });
}

async function getFile(env, db, userId, path) {
  const row = await db.prepare("SELECT version, obj FROM files WHERE user_id = ? AND path = ?").bind(userId, path).first();
  if (!row) throw new HttpError(404, "沒有這個檔案");
  const obj = await env.FILES.get(row.obj);
  if (!obj) throw new HttpError(404, "檔案內容不見了");
  return new Response(obj.body, { headers: { "Content-Type": "text/plain; charset=utf-8", "X-Version": String(row.version), "Cache-Control": "no-store" } });
}

// PUT with If-Match: <the version this text is based on> (0: a new file). The
// text goes to a new R2 object first; D1 points to it only if the version is
// still the base, so of two writers one wins and the other deletes its object.
async function putFile(request, env, db, userId, path) {
  const base = Number(request.headers.get("If-Match") ?? NaN);
  if (!Number.isInteger(base) || base < 0) throw new HttpError(428, "需要 If-Match（檔案的版本，新檔案是 0）");
  const text = await request.text();
  const size = enc.encode(text).length;
  if (size > MAX_FILE) throw new HttpError(413, "檔案太大（上限 1 MB）");
  const version = base + 1;
  const key = newObjectKey(userId);
  const mtime = now();
  const old = base > 0 ? await db.prepare("SELECT obj FROM files WHERE user_id = ? AND path = ? AND version = ?").bind(userId, path, base).first() : null;
  let changed = 0;
  if (base === 0) {
    const { n } = await db.prepare("SELECT COUNT(*) AS n FROM files WHERE user_id = ?").bind(userId).first();
    if (n >= MAX_FILES) throw new HttpError(413, `檔案太多（上限 ${MAX_FILES} 個）`);
    await env.FILES.put(key, text);
    changed = (await db.prepare("INSERT INTO files (user_id, path, version, size, mtime, obj) VALUES (?, ?, 1, ?, ?, ?) ON CONFLICT DO NOTHING").bind(userId, path, size, mtime, key).run()).meta.changes;
  } else if (old) {
    await env.FILES.put(key, text);
    changed = (await db.prepare("UPDATE files SET version = ?, size = ?, mtime = ?, obj = ? WHERE user_id = ? AND path = ? AND version = ?").bind(version, size, mtime, key, userId, path, base).run()).meta.changes;
  }
  if (!changed) {
    if (base === 0 || old) await env.FILES.delete(key);
    const row = await db.prepare("SELECT version FROM files WHERE user_id = ? AND path = ?").bind(userId, path).first();
    throw new HttpError(409, "檔案在別處改過了", { version: row?.version ?? 0 });
  }
  if (old) await env.FILES.delete(old.obj);
  return json({ path, version, size, mtime });
}

// DELETE ?version=N deletes only that version (409 when it changed); without it, any.
async function deleteFile(url, env, db, userId, path) {
  const want = url.searchParams.get("version");
  const row = await db.prepare("SELECT version, obj FROM files WHERE user_id = ? AND path = ?").bind(userId, path).first();
  if (!row) return json({ ok: true });
  if (want !== null && Number(want) !== row.version) throw new HttpError(409, "檔案在別處改過了", { version: row.version });
  const { changes } = (await db.prepare("DELETE FROM files WHERE user_id = ? AND path = ? AND version = ?").bind(userId, path, row.version).run()).meta;
  if (!changes) throw new HttpError(409, "檔案在別處改過了");
  await env.FILES.delete(row.obj);
  return json({ ok: true });
}

// --------------------------------------------------------------- shares

const SHARE_ID = /^[0-9a-f]{16}$/;

async function createShare(request, env, db, userId) {
  const { path, text } = await readJson(request);
  const p = filePath(encodeURIComponent(String(path || "")));
  if (typeof text !== "string") throw new HttpError(400, "缺少檔案內容");
  if (enc.encode(text).length > MAX_FILE) throw new HttpError(413, "檔案太大（上限 1 MB）");
  const id = randomHex(8);
  await env.FILES.put(`s/${id}`, text, { customMetadata: { path: p } });
  await db.prepare("INSERT INTO shares (id, user_id, path, created_at) VALUES (?, ?, ?, ?)").bind(id, userId, p, now()).run();
  return json({ id, path: p, url: `/s/${id}` });
}

async function listShares(db, userId) {
  const { results } = await db.prepare("SELECT id, path, created_at FROM shares WHERE user_id = ? ORDER BY created_at DESC").bind(userId).all();
  return json({ shares: results.map((s) => ({ ...s, url: `/s/${s.id}` })) });
}

async function deleteShare(env, db, userId, id) {
  const { changes } = (await db.prepare("DELETE FROM shares WHERE id = ? AND user_id = ?").bind(id, userId).run()).meta;
  if (changes) await env.FILES.delete(`s/${id}`);
  return json({ ok: true });
}

async function getShare(env, db, id) {
  const row = SHARE_ID.test(id) ? await db.prepare("SELECT path, created_at FROM shares WHERE id = ?").bind(id).first() : null;
  const obj = row && (await env.FILES.get(`s/${id}`));
  if (!obj) throw new HttpError(404, "這個分享連結不存在或已經取消");
  return json({ id, path: row.path, created_at: row.created_at, text: await obj.text() });
}

// ------------------------------------------------------------------- AI

const AI_MAX_BODY = 128 << 10;
const AI_MAX_MESSAGES = 20;
const aiEnabled = (env) => !!(env.AI_BASE_URL || env.AI);

const SYSTEM_PROMPT = `你是 rupy IDE 裡的程式助手，用繁體中文回答，簡短直接。

rupy 把有型別標註的 Python 子集編譯成 WebAssembly，在瀏覽器裡執行；同一支程式在 CPython 下輸出必須相同。寫給 rupy 的程式要遵守：
- 函式的參數與回傳值都要標型別（def f(xs: list[float], k: int = 3) -> float:）；空的 list、dict 要標型別（xs: list[int] = []）。
- 型別：int（64 位元）、float、bool、str、list、dict、set、tuple、X | None。一個變數只能有一種型別，list 的元素型別要一致。
- 可以用：dataclass、類別（單一繼承、property、運算子方法）、例外與 try/finally、comprehension、f-string、match、with open(...)（文字檔）、lambda 當 key= 參數、math、collections（Counter、defaultdict）、bisect、functools、sys、time、json.dumps、os.path、random（和 CPython 相同的亂數）、itertools、re（pattern 要寫成字串常值）。
- 瀏覽器（wasm）還不支援：generator（yield）、把函式當值傳遞、nonlocal、heapq、例外的自訂欄位、ruai.plot。需要時改寫，例如 generator 改成回傳 list。
- 頂層變數是常數，不能在函式裡重新指定；需要可變的狀態就用類別或傳參數。被 import 的模組只能定義函式、類別和常數。
- 套件：numpy（陣列、linalg、random.default_rng）、rstatistics（R 風格統計：mean、sd、t_test、lm、density 等；繪圖 g = rstatistics.Graphics(7.0, 7.0)，g.hist(x, main=..., xlab=..., ylab=...)、g.plot(x, y, ...)、g.boxplot、g.qqnorm，print(g.svg()) 會在 IDE 顯示成圖，g.save("a.svg") 存檔）。
- 工作區的檔案可以 import（同資料夾的 .py）或用 open() 讀。

回答程式問題時：
- 要給修改後的程式，就在一個 \`\`\`python 區塊裡給「完整」的內容（整個檔案；若問的是筆記本的一格，就只給那一格的完整內容），不要只給片段，也不要給好幾個 python 區塊。
- 先用一兩句話說明問題出在哪、怎麼改。`;

/** The day's request count of a user, after counting this one (429 over the limit). */
async function countAiRequest(env, db, userId) {
  const day = now().slice(0, 10);
  const limit = Number(env.AI_DAILY_LIMIT) || 100;
  const row = await db
    .prepare("INSERT INTO ai_usage (user_id, day, requests) VALUES (?, ?, 1) ON CONFLICT (user_id, day) DO UPDATE SET requests = requests + 1 RETURNING requests")
    .bind(userId, day)
    .first();
  if (row.requests > limit) throw new HttpError(429, `今天的 AI 額度（${limit} 次）用完了，明天再試`);
}

/** The messages for the model: the system prompt, the context (the file, the error) and the conversation. */
function aiMessages(body) {
  const msgs = Array.isArray(body.messages) ? body.messages.slice(-AI_MAX_MESSAGES) : [];
  const conv = msgs
    .filter((m) => (m?.role === "user" || m?.role === "assistant") && typeof m.content === "string")
    .map((m) => ({ role: m.role, content: m.content }));
  if (!conv.length || conv[conv.length - 1].role !== "user") throw new HttpError(400, "沒有問題");
  const c = body.context ?? {};
  let ctx = "";
  if (typeof c.path === "string" && typeof c.text === "string") {
    ctx += c.cell
      ? `使用者正在看筆記本 ${c.path} 的一格。它上面的程式格（會先執行）：\n\`\`\`python\n${String(c.before ?? "")}\n\`\`\`\n這一格：\n\`\`\`python\n${c.text}\n\`\`\`\n`
      : `使用者正在編輯 ${c.path}：\n\`\`\`python\n${c.text}\n\`\`\`\n`;
  }
  if (typeof c.error === "string" && c.error) ctx += `最近一次編譯或執行的錯誤：\n\`\`\`\n${c.error}\n\`\`\`\n`;
  if (Array.isArray(c.files) && c.files.length) ctx += `工作區的其他檔案：${c.files.filter((f) => typeof f === "string").slice(0, 50).join("、")}\n`;
  const system = SYSTEM_PROMPT + (ctx ? "\n\n目前的情況：\n" + ctx : "");
  return [{ role: "system", content: system }, ...conv];
}

/** Server-sent events of the reply: {"d": text} …, {"e": error} on failure, then [DONE]. */
async function aiChat(request, env, db, userId) {
  if (!aiEnabled(env)) throw new HttpError(503, "伺服器沒有設定 AI");
  const raw = await request.text();
  if (raw.length > AI_MAX_BODY) throw new HttpError(413, "內容太長（檔案太大或對話太長）");
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    throw new HttpError(400, "格式不對");
  }
  const messages = aiMessages(body);
  await countAiRequest(env, db, userId);

  const { readable, writable } = new TransformStream();
  const out = writable.getWriter();
  const send = (obj) => out.write(enc.encode(`data: ${JSON.stringify(obj)}\n\n`));
  (async () => {
    try {
      if (env.AI_BASE_URL) await streamOpenAI(env, messages, send);
      else await streamWorkersAI(env, messages, send);
    } catch (e) {
      await send({ e: "AI 連線失敗：" + e.message });
    }
    await out.write(enc.encode("data: [DONE]\n\n"));
    await out.close();
  })();
  return new Response(readable, { headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache" } });
}

/** The data lines of a server-sent event stream, as they arrive. */
async function* sseData(body) {
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line.startsWith("data:")) yield line.slice(5).trim();
    }
  }
}

async function streamOpenAI(env, messages, send) {
  const res = await fetch(env.AI_BASE_URL.replace(/\/+$/, "") + "/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(env.AI_API_KEY && { Authorization: "Bearer " + env.AI_API_KEY }) },
    body: JSON.stringify({ model: env.AI_MODEL, messages, stream: true, temperature: 0.2 }),
  });
  if (!res.ok) return send({ e: `AI 服務回應 ${res.status}：${(await res.text()).slice(0, 300)}` });
  if (!(res.headers.get("content-type") ?? "").includes("event-stream")) {
    const j = await res.json();
    const text = j.choices?.[0]?.message?.content;
    return send(text ? { d: text } : { e: "AI 沒有回傳內容" });
  }
  for await (const data of sseData(res.body)) {
    if (data === "[DONE]") break;
    let j;
    try {
      j = JSON.parse(data);
    } catch {
      continue;
    }
    if (j.error) return send({ e: j.error.message ?? String(j.error) });
    const delta = j.choices?.[0]?.delta;
    // a reasoning model's thinking, shown folded
    if (delta?.reasoning_content) await send({ r: delta.reasoning_content });
    if (delta?.content) await send({ d: delta.content });
  }
}

async function streamWorkersAI(env, messages, send) {
  const stream = await env.AI.run(env.AI_MODEL || "@cf/meta/llama-3.1-8b-instruct", { messages, stream: true });
  for await (const data of sseData(stream)) {
    if (data === "[DONE]") break;
    try {
      const j = JSON.parse(data);
      if (j.response) await send({ d: j.response });
    } catch {}
  }
}

// --------------------------------------------------------------- schema

let schemaReady = false;
async function ensureSchema(db) {
  if (schemaReady) return;
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE,
      pass_hash TEXT NOT NULL,
      pass_salt TEXT NOT NULL,
      created_at TEXT NOT NULL)`),
    db.prepare(`CREATE TABLE IF NOT EXISTS files (
      user_id INTEGER NOT NULL,
      path TEXT NOT NULL,
      version INTEGER NOT NULL,
      size INTEGER NOT NULL,
      mtime TEXT NOT NULL,
      obj TEXT NOT NULL,
      PRIMARY KEY (user_id, path))`),
    db.prepare(`CREATE TABLE IF NOT EXISTS shares (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL,
      path TEXT NOT NULL,
      created_at TEXT NOT NULL)`),
    db.prepare("CREATE INDEX IF NOT EXISTS idx_shares_user ON shares (user_id, created_at)"),
    db.prepare(`CREATE TABLE IF NOT EXISTS ai_usage (
      user_id INTEGER NOT NULL,
      day TEXT NOT NULL,
      requests INTEGER NOT NULL,
      PRIMARY KEY (user_id, day))`),
  ]);
  schemaReady = true;
}

// --------------------------------------------------------------- router

async function route(request, env, url) {
  const p = url.pathname;
  const method = request.method;
  const db = env.DB;
  await ensureSchema(db);
  let m;

  if ((m = p.match(/^\/api\/s\/([^/]+)$/)) && method === "GET") return getShare(env, db, m[1]);

  // CSRF: an API that changes data only takes requests from this site
  if (method !== "GET" && method !== "HEAD") {
    const site = request.headers.get("sec-fetch-site");
    const origin = request.headers.get("origin");
    if ((site && site !== "same-origin" && site !== "none") || (origin && origin !== url.origin)) throw new HttpError(403, "不接受跨站請求");
  }

  if (p === "/api/me" && method === "GET") {
    if (!env.AUTH_SECRET) return json({ accounts: false, user: null, ai: false });
    const id = await currentUserId(request, env);
    const user = id && (await db.prepare("SELECT id, email FROM users WHERE id = ?").bind(id).first());
    return json({ accounts: true, user: user ?? null, ai: aiEnabled(env) });
  }
  if (!env.AUTH_SECRET) throw new HttpError(503, "伺服器沒有設定 AUTH_SECRET，不能使用帳號");
  if (p === "/api/register" && method === "POST") return register(request, env, db);
  if (p === "/api/login" && method === "POST") return login(request, env, db);
  if (p === "/api/logout" && method === "POST") return json({ ok: true }, 200, { "Set-Cookie": `${COOKIE}=; Path=/; Max-Age=0` });

  const userId = await currentUserId(request, env);
  if (!userId) throw new HttpError(401, "請先登入");

  if (p === "/api/files" && method === "GET") return listFiles(db, userId);
  if ((m = p.match(/^\/api\/files\/(.+)$/))) {
    const path = filePath(m[1]);
    if (method === "GET") return getFile(env, db, userId, path);
    if (method === "PUT") return putFile(request, env, db, userId, path);
    if (method === "DELETE") return deleteFile(url, env, db, userId, path);
  }
  if (p === "/api/shares" && method === "GET") return listShares(db, userId);
  if (p === "/api/shares" && method === "POST") return createShare(request, env, db, userId);
  if ((m = p.match(/^\/api\/shares\/([0-9a-f]+)$/)) && method === "DELETE") return deleteShare(env, db, userId, m[1]);
  if (p === "/api/ai/chat" && method === "POST") return aiChat(request, env, db, userId);
  throw new HttpError(404, "not found");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/health") return json({ ok: true, name: "rupy-ide" });
    if (url.pathname.startsWith("/s/")) return env.ASSETS.fetch(new Request(new URL("/share.html", url), request));
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
    try {
      return await route(request, env, url);
    } catch (e) {
      if (e instanceof HttpError) return json({ error: e.message, ...e.extra }, e.status);
      console.error(e);
      return json({ error: "伺服器錯誤：" + e.message }, 500);
    }
  },
};
