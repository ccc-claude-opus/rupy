// The rupy IDE's API. Programs compile and run in the browser; the server keeps
// accounts, each account's files and read-only share links.
//   /api/register, /api/login, /api/logout, /api/me   accounts (PBKDF2, HMAC-signed cookie)
//   /api/files[/<path>]                               the account's files (list, get, put, delete)
//   /api/shares[/<id>]                                share links of the account (create, list, delete)
//   /api/s/<id>                                       a shared file (public)
//   /s/<id>                                           the share page (public/share.html)
// Files: a row in D1 (path, version, size, mtime, obj) and the text in R2 under
// obj = u/<user>/<random>, a new object for every write; a PUT names the version
// it is based on (If-Match) and gets 409 when the file changed in between. Shares are snapshots in R2 (s/<id>).
// AUTH_SECRET (.dev.vars) signs the cookie; without it there are no accounts.

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
    if (!env.AUTH_SECRET) return json({ accounts: false, user: null });
    const id = await currentUserId(request, env);
    const user = id && (await db.prepare("SELECT id, email FROM users WHERE id = ?").bind(id).first());
    return json({ accounts: true, user: user ?? null });
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
