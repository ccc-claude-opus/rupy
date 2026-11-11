// The AI assistant's panel: a conversation per file with the server's
// /api/ai/chat (a stream of server-sent events). The code of a reply is compiled
// in the background; when it does not compile, the error goes back to the model
// (at most twice). "See the changes" shows a diff, and applying it is one edit
// that Ctrl/⌘ + Z undoes.

const RETRIES = 2;

/** The last ```python block of a reply (the model is asked for one, complete), or null. */
export function extractCode(text) {
  const blocks = [...text.matchAll(/```(?:python|py)?[ \t]*\n([\s\S]*?)```/g)];
  if (!blocks.length) return null;
  const code = blocks[blocks.length - 1][1];
  return code.trim() ? code.replace(/\s+$/, "") + "\n" : null;
}

/** A reply with its <think>…</think> (some models think in the text) taken out: { thinking, answer }. */
export function splitThinking(text) {
  let thinking = "";
  const answer = text.replace(/<think>([\s\S]*?)(<\/think>|$)/g, (_, t) => {
    thinking += t;
    return "";
  });
  return { thinking: thinking.trim(), answer: answer.replace(/^\s+/, "") };
}

/** The data of a stream of server-sent events, as they arrive. */
async function* events(res) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const ev = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = ev.replace(/^data: ?/, "");
      if (data === "[DONE]") return;
      try {
        yield JSON.parse(data);
      } catch {}
    }
  }
}

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

export class AiPanel {
  /**
   * opts:
   *   key() → the conversation's key (the open file), or null
   *   context() → (a promise of) { path, text, cell?, before?, error?, files } for the server
   *   verify(code) → Promise<error text | null> (compile the code in place of the file or cell)
   *   original() → the text the code would replace; apply(code) puts it in
   *   showDiff(old, new) → Promise<boolean> (the user applies it)
   *   render(markdown) → HTML
   *   enabled() → null, or why the assistant cannot be used (not signed in)
   */
  constructor(root, opts) {
    this.root = root;
    this.opts = opts;
    this.log = root.querySelector(".ai-log");
    this.input = root.querySelector("textarea");
    this.sendBtn = root.querySelector(".ai-send");
    this.chats = new Map(); // key → { messages: [{ role, content }], el }
    this.busy = null; // the AbortController of the reply being received
    root.querySelector("form").onsubmit = (e) => {
      e.preventDefault();
      if (this.busy) return this.busy.abort();
      const text = this.input.value.trim();
      if (!text) return;
      this.input.value = "";
      this.ask(text);
    };
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        root.querySelector("form").requestSubmit();
      }
    });
    root.querySelector(".ai-new").onclick = () => {
      const key = this.opts.key();
      if (!key || this.busy) return;
      this.chats.delete(key);
      this.show();
    };
  }

  /** The conversation of the open file. */
  chat() {
    const key = this.opts.key() ?? "";
    let c = this.chats.get(key);
    if (!c) {
      c = { messages: [], el: el("div", "ai-chat") };
      const hint = el("p", "muted", "問 rupy 的問題，或請它修改這個檔案。它給的程式會先編譯驗證，套用前可以看差異。");
      c.el.append(hint);
      this.chats.set(key, c);
    }
    return c;
  }

  /** Show the open file's conversation (after switching files). */
  show() {
    const why = this.opts.enabled();
    this.root.querySelector(".ai-ctx").textContent = this.opts.key() ?? "";
    this.input.disabled = !!why;
    this.sendBtn.disabled = !!why;
    if (why) return this.log.replaceChildren(el("p", "muted", why));
    this.log.replaceChildren(this.chat().el);
    this.scroll();
  }

  scroll() {
    this.log.scrollTop = this.log.scrollHeight;
  }

  setBusy(ctrl) {
    this.busy = ctrl;
    this.sendBtn.textContent = ctrl ? "停止" : "送出";
    this.sendBtn.classList.toggle("run", !ctrl);
  }

  /** Ask a question (a user's, or the compile error of the last reply's code: `attempt` > 0). */
  async ask(text, attempt = 0) {
    if (this.busy || this.opts.enabled()) return;
    const key = this.opts.key();
    const c = this.chat();
    c.messages.push({ role: "user", content: text });
    c.el.append(el("div", "ai-msg user" + (attempt ? " auto" : ""), text));
    const msg = el("div", "ai-msg assistant");
    const think = el("details", "ai-think");
    think.append(el("summary", null, "思考過程"), el("pre"));
    think.hidden = true;
    const body = el("div", "ai-body md-view");
    const foot = el("div", "ai-foot");
    msg.append(think, body, foot);
    c.el.append(msg);
    this.scroll();

    const ctrl = new AbortController();
    this.setBusy(ctrl);
    let raw = "", reasoning = "", failed = null;
    let frame = 0;
    const draw = () => {
      frame = 0;
      const { thinking, answer } = splitThinking(raw);
      const t = (reasoning + (reasoning && thinking ? "\n" : "") + thinking).trim();
      think.hidden = !t;
      think.querySelector("pre").textContent = t;
      body.innerHTML = this.opts.render(answer || (t ? "" : "…"));
      this.scroll();
    };
    try {
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: c.messages, context: await this.opts.context() }),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.error ?? res.statusText);
      for await (const ev of events(res)) {
        if (ev.e) failed = ev.e;
        if (ev.d) raw += ev.d;
        if (ev.r) reasoning += ev.r;
        if (!frame) frame = requestAnimationFrame(draw);
      }
    } catch (e) {
      failed = e.name === "AbortError" ? "已停止" : e.message;
    }
    cancelAnimationFrame(frame);
    draw();
    this.setBusy(null);
    const { answer } = splitThinking(raw);
    if (answer) c.messages.push({ role: "assistant", content: answer });
    else c.messages.pop(); // nothing came back: the question can be asked again
    if (failed) foot.append(el("span", "stderr", failed));
    const code = extractCode(answer);
    if (!code || this.opts.key() !== key) return;

    const state = el("span", "muted", "編譯驗證中…");
    foot.prepend(state);
    const error = await this.opts.verify(code);
    if (this.opts.key() !== key) return;
    if (error && attempt < RETRIES && !failed) {
      state.textContent = "✗ 編譯錯誤，請 AI 再修正";
      state.className = "stderr";
      return this.ask(`這段程式在 rupy 編譯失敗：\n${error}\n請修正，同樣用一個 python 區塊給完整的內容。`, attempt + 1);
    }
    state.textContent = error ? "✗ 仍然編譯不過：" + error.split("\n")[0] : "✓ 編譯通過";
    state.className = error ? "stderr" : "ok";
    const apply = el("button", error ? "" : "run", "看差異並套用");
    apply.onclick = async () => {
      if (this.opts.key() !== key) return;
      if (await this.opts.showDiff(this.opts.original(), code)) {
        this.opts.apply(code);
        apply.textContent = "已套用（Ctrl/⌘ + Z 復原）";
        apply.disabled = true;
      }
    };
    foot.append(apply);
    this.scroll();
  }
}
