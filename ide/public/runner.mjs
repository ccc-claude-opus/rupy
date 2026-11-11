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
        else if (data.type === "file") job.onFile?.(data.path, data.text);
        else if (data.type === "done") {
          this.jobs.delete(data.id);
          job.resolve(data);
        }
      };
    });
  }

  /**
   * Compile (op "compile") or compile and run (op "run") `project`, { main, files:
   * { path: text } } (main, the modules it imports, and the files it may read);
   * onFile(path, text): a file the program wrote. Resolves with the "done" message.
   */
  async request(op, project, { stdin = "", onOutput, onFile } = {}) {
    await this.ready;
    const id = ++this.seq;
    return new Promise((resolve) => {
      this.jobs.set(id, { resolve, onOutput, onFile });
      this.worker.postMessage({ id, op, project, stdin });
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

/** A compile error ({ file, line, msg, hint }) as text. */
export function formatError(e) {
  return `${e.line ? `${e.file} 第 ${e.line} 行` : e.file}：${e.msg}${e.hint ? `\n  提示：${e.hint}` : ""}`;
}

/** The message of an error's marker. */
export const markerMessage = (e) => e.msg + (e.hint ? `\n提示：${e.hint}` : "");
