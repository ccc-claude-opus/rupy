// Keeps the local files (fs.mjs) and the account's files on the server in step.
// Local first: edits are saved locally and uploaded a moment later; the server's
// changes are downloaded when they come from elsewhere. When both changed, the
// server's text wins and the local text is kept as <name>.conflict-<time><ext>.

export async function api(path, { method = "GET", body, headers = {} } = {}) {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { ...(body !== undefined && typeof body !== "string" && { "Content-Type": "application/json" }), ...headers },
    body: body === undefined || typeof body === "string" ? body : JSON.stringify(body),
  });
  const type = res.headers.get("content-type") ?? "";
  const data = type.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const e = new Error(data?.error ?? res.statusText);
    e.status = res.status;
    e.data = data;
    throw e;
  }
  return { data, headers: res.headers };
}

const fileUrl = (path) => "/api/files/" + path.split("/").map(encodeURIComponent).join("/");

function conflictName(path) {
  const t = new Date().toISOString().replace(/\D/g, "").slice(0, 12);
  const m = path.match(/^(.*?)(\.\w+)?$/);
  return `${m[1]}.conflict-${t}${m[2] ?? ""}`;
}

export class Sync {
  /** opts: before() (flush pending saves), onStatus(text, kind), onRemote(paths) (files the server changed here). */
  constructor(fs, opts) {
    this.fs = fs;
    this.opts = opts;
    this.running = null;
    this.again = false;
    this.timer = null;
    setInterval(() => this.schedule(0), 60_000);
    addEventListener("focus", () => this.schedule(0));
    addEventListener("online", () => this.schedule(0));
  }

  schedule(delay = 1500) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.run(), delay);
  }

  /** Sync now (if a sync is running, once more after it). */
  async run() {
    if (this.running) {
      this.again = true;
      return this.running;
    }
    this.running = this.pass().finally(() => (this.running = null));
    await this.running;
    if (this.again) {
      this.again = false;
      return this.run();
    }
  }

  async pass() {
    const { fs, opts } = this;
    await opts.before?.();
    opts.onStatus("同步中…", "busy");
    const changed = new Set();
    let failed = null;
    try {
      const remote = new Map((await api("/api/files")).data.files.map((f) => [f.path, f]));
      for (const local of await fs.all()) {
        const r = remote.get(local.path);
        remote.delete(local.path);
        try {
          await this.one(local, r, changed);
        } catch (e) {
          if (e.status === 409) this.again = true; // changed on the server meanwhile: once more
          else if (e.status >= 400 && e.status < 500) failed = `${local.path}：${e.message}`;
          else throw e;
        }
      }
      for (const r of remote.values()) await this.download(r.path, changed, undefined);
    } catch (e) {
      failed = e.status === 401 ? "登入已過期，請重新登入" : e.status ? e.message : "離線，稍後再試";
      if (!e.status || e.status >= 500) this.schedule(15_000);
    }
    if (changed.size) opts.onRemote([...changed]);
    opts.onStatus(failed ? "同步失敗：" + failed : "已同步", failed ? "error" : "ok");
  }

  async one(local, r, changed) {
    const { fs } = this;
    if (local.deleted) {
      if (r) {
        try {
          await api(fileUrl(local.path) + "?version=" + local.version, { method: "DELETE" });
        } catch (e) {
          if (e.status !== 409) throw e;
          // changed elsewhere after we deleted it: keep the server's
          await fs.purge(local.path);
          return this.download(local.path, changed, undefined);
        }
      }
      return fs.purge(local.path);
    }
    if (!r) {
      if (local.version && !local.dirty) {
        // deleted elsewhere
        await fs.purge(local.path);
        changed.add(local.path);
        return;
      }
      return this.upload(local, 0);
    }
    if (local.dirty) {
      if (local.version === r.version) return this.upload(local, r.version);
      // both changed: keep ours under another name, take theirs
      const name = conflictName(local.path);
      await fs.set({ ...local, path: name, version: 0, dirty: true, rev: 1 });
      changed.add(name);
      this.again = true;
      return this.download(local.path, changed, local.rev);
    }
    if (local.version !== r.version) return this.download(local.path, changed, local.rev);
  }

  async upload(local, base) {
    const { data } = await api(fileUrl(local.path), { method: "PUT", body: local.text, headers: { "If-Match": String(base), "Content-Type": "text/plain; charset=utf-8" } });
    await this.fs.markSynced(local.path, data.version, local.rev);
  }

  /** Take the server's text, unless the file was written here since we looked (`rev`: its rev then). */
  async download(path, changed, rev) {
    const { data, headers } = await api(fileUrl(path));
    const now = await this.fs.get(path);
    if (now && now.rev !== rev) {
      this.again = true;
      return;
    }
    await this.fs.set({ path, text: data, mtime: Date.now(), version: Number(headers.get("x-version")), dirty: false, rev: (now?.rev ?? 0) + 1, deleted: false });
    changed.add(path);
  }
}
