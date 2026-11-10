// The page's side of runner.worker.mjs: one worker per job kind. `stop()`
// terminates the worker (the only way to end an endless loop) and starts a new one.
export class Runner {
  constructor() {
    this.seq = 0;
    this.jobs = new Map();
    this.start();
  }

  start() {
    this.worker = new Worker(new URL("./runner.worker.mjs", import.meta.url), { type: "module" });
    this.ready = new Promise((resolve, reject) => {
      this.worker.onerror = (e) => reject(new Error(e.message || "the runner failed to load"));
      this.worker.onmessage = ({ data }) => {
        if (data.type === "ready") return resolve();
        const job = this.jobs.get(data.id);
        if (!job) return;
        if (data.type === "out") job.onOutput?.(data.fd, data.text);
        else if (data.type === "done") {
          this.jobs.delete(data.id);
          job.resolve(data);
        }
      };
    });
  }

  /** Compile (op "compile") or compile and run (op "run"); resolves with the "done" message. */
  async request(op, src, { stdin = "", onOutput } = {}) {
    await this.ready;
    const id = ++this.seq;
    return new Promise((resolve) => {
      this.jobs.set(id, { resolve, onOutput });
      this.worker.postMessage({ id, op, src, stdin });
    });
  }

  get busy() {
    return this.jobs.size > 0;
  }

  /** End every job (they resolve as stopped) and start a fresh worker. */
  stop() {
    this.worker.terminate();
    for (const job of this.jobs.values()) job.resolve({ type: "done", stopped: true });
    this.jobs.clear();
    this.start();
  }
}

/** The line numbers of a compile error: "line 3: …" or "geometry.py line 3: …" (null: main file only). */
export function errorLines(message) {
  const out = [];
  for (const m of message.matchAll(/(?:^|\n)(?:(\S+\.py) )?line (\d+): ([^\n]*)/g)) out.push({ file: m[1] ?? null, line: +m[2], msg: m[3] });
  return out;
}
