// The workspace's files in IndexedDB; in memory when IndexedDB is unavailable
// (a private window). A record: { path, text, mtime, version, dirty, rev, deleted }.
// `version` is the server's version the text is based on (0: never synced),
// `dirty` says the text changed since, `rev` counts local writes, and a deleted
// file that the server has stays as a tombstone until sync.mjs deletes it there.
// Each account has its own database (rupy-ide-u<id>); without one, "rupy-ide".
const STORE = "files";

function open(name) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(name, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "path" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

const done = (req) => new Promise((resolve, reject) => {
  req.onsuccess = () => resolve(req.result);
  req.onerror = () => reject(req.error);
});

export const dbName = (userId) => (userId ? `rupy-ide-u${userId}` : "rupy-ide");

export function deleteFs(name) {
  return new Promise((resolve) => {
    const req = indexedDB.deleteDatabase(name);
    req.onsuccess = req.onerror = req.onblocked = () => resolve();
  });
}

/** onWrite(): called after put / remove (to schedule a sync). */
export async function openFs(name = dbName(null), { onWrite } = {}) {
  let raw;
  try {
    const db = await open(name);
    const store = (mode) => db.transaction(STORE, mode).objectStore(STORE);
    raw = {
      persistent: true,
      all: () => done(store("readonly").getAll()),
      get: async (path) => (await done(store("readonly").get(path))) ?? null,
      set: async (rec) => void (await done(store("readwrite").put(rec))),
      purge: async (path) => void (await done(store("readwrite").delete(path))),
      close: () => db.close(),
    };
  } catch {
    const mem = new Map();
    raw = {
      persistent: false,
      all: async () => [...mem.values()],
      get: async (path) => mem.get(path) ?? null,
      set: async (rec) => void mem.set(rec.path, rec),
      purge: async (path) => void mem.delete(path),
      close: () => {},
    };
  }
  const fs = {
    ...raw,
    /** The files (not the tombstones), by path. */
    list: async () => (await raw.all()).filter((r) => !r.deleted).sort((a, b) => a.path.localeCompare(b.path)),
    get: async (path) => {
      const r = await raw.get(path);
      return r && !r.deleted ? r : null;
    },
    put: async (path, text) => {
      const old = await raw.get(path);
      await raw.set({ path, text, mtime: Date.now(), version: old?.version ?? 0, dirty: true, rev: (old?.rev ?? 0) + 1, deleted: false });
      onWrite?.();
    },
    remove: async (path) => {
      const old = await raw.get(path);
      if (old?.version) await raw.set({ ...old, text: "", mtime: Date.now(), dirty: true, rev: old.rev + 1, deleted: true });
      else await raw.purge(path);
      onWrite?.();
    },
    /** After an upload of local write `rev`: the file is at `version` (and clean unless written since). */
    markSynced: async (path, version, rev) => {
      const r = await raw.get(path);
      if (!r) return;
      await raw.set({ ...r, version, dirty: r.rev !== rev });
    },
  };
  return fs;
}
