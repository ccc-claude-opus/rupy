// The workspace's files in IndexedDB ({ path, text, mtime }); in memory when
// IndexedDB is unavailable (a private window). Cloud storage comes in M3.
const DB = "rupy-ide", STORE = "files";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "path" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

const done = (req) => new Promise((resolve, reject) => {
  req.onsuccess = () => resolve(req.result);
  req.onerror = () => reject(req.error);
});

export async function openFs() {
  let db = null;
  try {
    db = await open();
  } catch {}
  if (!db) {
    const mem = new Map();
    return {
      persistent: false,
      list: async () => [...mem.values()].sort((a, b) => a.path.localeCompare(b.path)),
      get: async (path) => mem.get(path) ?? null,
      put: async (path, text) => void mem.set(path, { path, text, mtime: Date.now() }),
      remove: async (path) => void mem.delete(path),
    };
  }
  const store = (mode) => db.transaction(STORE, mode).objectStore(STORE);
  return {
    persistent: true,
    list: async () => (await done(store("readonly").getAll())).sort((a, b) => a.path.localeCompare(b.path)),
    get: async (path) => (await done(store("readonly").get(path))) ?? null,
    put: async (path, text) => void (await done(store("readwrite").put({ path, text, mtime: Date.now() }))),
    remove: async (path) => void (await done(store("readwrite").delete(path))),
  };
}
