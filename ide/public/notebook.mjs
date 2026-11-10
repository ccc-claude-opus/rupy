// The notebook view: a Monaco editor per cell, outputs under code cells,
// rendered Markdown (double-click to edit). Running cell k runs code cells
// 0..k as one program (nbformat.mjs) and splits the output among them.
import { parseNotebook, serializeNotebook, buildProgram, locate, outputSplitter, newCell } from "./nbformat.mjs";
import { errorLines } from "./runner.mjs";

let markdownModule = null;
const markdown = () => (markdownModule ??= import("./markdown.mjs"));

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

function button(label, title, fn) {
  const b = el("button", null, label);
  b.title = title;
  b.setAttribute("aria-label", title);
  b.onclick = (e) => {
    e.stopPropagation();
    fn();
  };
  return b;
}

const EDITOR_OPTIONS = {
  automaticLayout: false,
  fontSize: 13,
  tabSize: 4,
  insertSpaces: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  lineNumbersMinChars: 3,
  folding: false,
  glyphMargin: false,
  overviewRulerLanes: 0,
  hideCursorInOverviewRuler: true,
  renderLineHighlight: "none",
  padding: { top: 6, bottom: 6 },
  scrollbar: { vertical: "hidden", alwaysConsumeMouseWheel: false, horizontalScrollbarSize: 6 },
};

export class NotebookView {
  /**
   * opts: monaco, runner, stdin() → text, onChange() (save), onEdit() (check
   * later), onRunRequest(upto) (the page runs through run(), with its buttons).
   */
  constructor(root, opts) {
    this.root = root;
    this.opts = opts;
    this.items = [];
    this.active = null;
    this.counter = 0;
    this.resize = new ResizeObserver(() => this.items.forEach((it) => it.fit()));
    this.resize.observe(root);
  }

  /** Show the .ipynb text (throws when it is not a notebook). */
  load(text) {
    this.nb = parseNotebook(text);
    this.counter = Math.max(0, ...this.nb.cells.map((c) => c.count ?? 0));
    this.root.replaceChildren(this.addBar(0));
    this.items = this.nb.cells.map((cell) => this.makeItem(cell));
    for (const it of this.items) this.root.append(it.el);
    this.setActive(this.items[0]);
  }

  text() {
    return serializeNotebook(this.nb);
  }

  dispose() {
    this.resize.disconnect();
    for (const it of this.items) it.editor.dispose();
    this.items = [];
    this.root.replaceChildren();
  }

  // ------------------------------------------------------------- cells

  makeItem(cell) {
    const { monaco } = this.opts;
    const code = cell.type === "code";
    const item = { cell };
    item.el = el("div", `cell ${cell.type}`);
    const gutter = el("div", "gutter");
    if (code) {
      gutter.append(button("▶", "執行到這一格（Shift + Enter）", () => this.opts.onRunRequest(this.index(item))));
      item.countEl = el("span", "count");
      gutter.append(item.countEl);
    }
    const body = el("div", "body");
    const host = el("div", "cell-editor");
    body.append(host);
    if (code) {
      item.out = el("pre", "cell-out");
      body.append(item.out);
    } else {
      item.view = el("div", "md-view");
      item.view.title = "點兩下編輯";
      item.view.ondblclick = () => this.editMarkdown(item);
      body.append(item.view);
    }
    const tools = el("div", "cell-tools");
    tools.append(
      button("↑", "上移", () => this.move(item, -1)),
      button("↓", "下移", () => this.move(item, 1)),
      button("✕", "刪除這一格", () => this.remove(item)),
    );
    const row = el("div", "cell-row");
    row.append(gutter, body, tools);
    item.el.append(row, this.addBar(item));
    item.el.addEventListener("mousedown", () => this.setActive(item));

    const editor = monaco.editor.create(host, {
      ...EDITOR_OPTIONS,
      value: cell.source,
      language: code ? "python" : "markdown",
      wordWrap: code ? "off" : "on",
      lineNumbers: code ? "on" : "off",
    });
    item.editor = editor;
    item.host = host;
    item.fit = () => {
      if (host.hidden) return;
      const h = Math.max(editor.getContentHeight(), 30);
      host.style.height = h + "px";
      editor.layout({ width: host.clientWidth, height: h });
    };
    editor.onDidContentSizeChange(item.fit);
    editor.onDidChangeModelContent(() => {
      cell.source = editor.getValue();
      this.opts.onChange();
      if (code) this.opts.onEdit();
    });
    editor.onDidFocusEditorText(() => this.setActive(item));
    if (!code) editor.onDidBlurEditorText(() => this.renderMarkdown(item));
    // addAction, not addCommand: a command's key binding would go to the last editor made
    editor.addAction({ id: "rupy.runAdvance", label: "執行並到下一格", keybindings: [monaco.KeyMod.Shift | monaco.KeyCode.Enter], run: () => this.runAndAdvance(item) });
    editor.addAction({
      id: "rupy.run",
      label: "執行這一格",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
      run: () => (code ? this.opts.onRunRequest(this.index(item)) : this.renderMarkdown(item)),
    });
    if (code) this.showOutputs(item);
    else if (cell.source.trim()) this.renderMarkdown(item);
    requestAnimationFrame(item.fit);
    return item;
  }

  addBar(after) {
    const bar = el("div", "add-bar");
    const at = () => (typeof after === "number" ? after : this.index(after) + 1);
    bar.append(button("＋ 程式碼", "在這裡新增程式碼格", () => this.insert(at(), "code")), button("＋ 文字", "在這裡新增文字格", () => this.insert(at(), "markdown")));
    return bar;
  }

  index(item) {
    return this.items.indexOf(item);
  }

  setActive(item) {
    if (this.active === item) return;
    this.active?.el.classList.remove("active");
    this.active = item ?? null;
    item?.el.classList.add("active");
  }

  insert(at, type) {
    const cell = newCell(type);
    this.nb.cells.splice(at, 0, cell);
    const item = this.makeItem(cell);
    const before = this.items[at]?.el ?? null;
    this.root.insertBefore(item.el, before);
    this.items.splice(at, 0, item);
    this.setActive(item);
    if (type === "markdown") this.editMarkdown(item);
    else item.editor.focus();
    this.changed();
    return item;
  }

  remove(item) {
    const i = this.index(item);
    if (item.cell.source.trim() && !confirm("刪除這一格？")) return;
    item.editor.dispose();
    item.el.remove();
    this.items.splice(i, 1);
    this.nb.cells.splice(i, 1);
    this.setActive(this.items[Math.min(i, this.items.length - 1)]);
    this.changed();
  }

  move(item, by) {
    const i = this.index(item), j = i + by;
    if (j < 0 || j >= this.items.length) return;
    [this.items[i], this.items[j]] = [this.items[j], this.items[i]];
    [this.nb.cells[i], this.nb.cells[j]] = [this.nb.cells[j], this.nb.cells[i]];
    const [a, b] = by < 0 ? [item, this.items[i]] : [this.items[i], item];
    this.root.insertBefore(a.el, b.el);
    this.changed();
  }

  changed() {
    this.opts.onChange();
    this.opts.onEdit();
  }

  // ---------------------------------------------------------- markdown

  editMarkdown(item) {
    item.view.hidden = true;
    item.host.hidden = false;
    item.fit();
    item.editor.focus();
  }

  async renderMarkdown(item) {
    const src = item.cell.source;
    if (!src.trim()) return; // an empty text cell stays in the editor
    try {
      item.view.innerHTML = (await markdown()).renderMarkdown(src);
    } catch (e) {
      item.view.textContent = "Markdown 無法顯示：" + e.message;
    }
    item.host.hidden = true;
    item.view.hidden = false;
  }

  runAndAdvance(item) {
    const i = this.index(item);
    if (item.cell.type === "code") this.opts.onRunRequest(i);
    else this.renderMarkdown(item);
    const next = this.items[i + 1];
    if (!next) return this.insert(i + 1, "code");
    this.setActive(next);
    if (next.cell.type === "code") next.editor.focus();
  }

  // ------------------------------------------------------------ outputs

  showOutputs(item) {
    item.out.replaceChildren(...item.cell.outputs.map((o) => el("span", o.name === "stderr" ? "stderr" : "", o.text)));
    item.out.hidden = item.cell.outputs.length === 0;
    item.countEl.textContent = item.cell.count ? `[${item.cell.count}]` : "[ ]";
  }

  appendOutput(i, name, text) {
    const item = this.items[i];
    if (!item?.out || !text) return;
    const outs = item.cell.outputs;
    const last = outs[outs.length - 1];
    if (last && last.name === name) {
      last.text += text;
      item.out.lastChild.textContent += text;
    } else {
      outs.push({ name, text });
      item.out.append(el("span", name === "stderr" ? "stderr" : "", text));
    }
    item.out.hidden = false;
  }

  // ---------------------------------------------------------------- run

  /** The index to run for the toolbar's Run: the active cell, or the last cell. */
  activeIndex() {
    return this.active ? this.index(this.active) : this.items.length - 1;
  }

  /** Run code cells 0..upto; resolves with the runner's "done" message (plus `cells`, how many ran). */
  async run(upto) {
    const { monaco, runner } = this.opts;
    const { src, starts } = buildProgram(this.nb.cells, upto);
    const ran = starts.map((s) => s.cell);
    for (const i of ran) {
      const it = this.items[i];
      it.cell.outputs = [];
      it.cell.count = null;
      this.showOutputs(it);
      it.countEl.textContent = "[*]";
      it.el.classList.add("queued");
      monaco.editor.setModelMarkers(it.editor.getModel(), "rupy", []);
    }
    const started = [];
    const split = outputSplitter((i, text) => {
      if (started[started.length - 1] !== i) {
        const prev = this.items[started[started.length - 1]];
        prev?.el.classList.remove("running");
        started.push(i);
        this.items[i].el.classList.replace("queued", "running");
      }
      this.appendOutput(i, "stdout", text);
    });
    const r = ran.length
      ? await runner.request("run", src, {
          stdin: this.opts.stdin(),
          onOutput: (fd, text) => (fd === 1 ? split.feed(text) : this.appendOutput(split.current >= 0 ? split.current : ran[0], "stderr", text)),
        })
      : { type: "done", code: 0, compileMs: 0, runMs: 0, bytes: 0 };
    if (r.error) this.showCompileError(r.error, starts);
    else if (r.stopped) this.appendOutput(split.current >= 0 ? split.current : ran[0], "stderr", "[已停止]\n");
    for (const i of ran) {
      const it = this.items[i];
      it.el.classList.remove("queued", "running");
      if (!r.error && started.includes(i)) it.cell.count = ++this.counter;
      this.showOutputs(it);
    }
    this.opts.onChange();
    return { ...r, cells: started.length };
  }

  showCompileError(error, starts) {
    const found = errorLines(error).filter((e) => e.file === null);
    if (!found.length) return this.appendOutput(starts[starts.length - 1]?.cell ?? 0, "stderr", error + "\n");
    for (const { line, msg } of found) {
      const at = locate(starts, line) ?? { cell: starts[0].cell, line: 1 };
      this.appendOutput(at.cell, "stderr", `第 ${at.line} 行：${msg}\n`);
    }
    this.setMarkers(error, starts);
  }

  // ---------------------------------------------------- errors as you type

  /** Compile every code cell with `checker`; mark the errors in their cells. */
  async check(checker) {
    const { src, starts } = buildProgram(this.nb.cells);
    const r = await checker.request("compile", src);
    if (r.stopped || !this.items.length) return false;
    this.setMarkers(r.error, starts);
    return true;
  }

  setMarkers(error, starts) {
    const { monaco } = this.opts;
    const byCell = new Map();
    for (const { line, msg, file } of error ? errorLines(error) : []) {
      if (file !== null) continue;
      const at = locate(starts, line);
      if (!at) continue;
      if (!byCell.has(at.cell)) byCell.set(at.cell, []);
      byCell.get(at.cell).push({ line: at.line, msg });
    }
    this.items.forEach((it, i) => {
      if (it.cell.type !== "code") return;
      const model = it.editor.getModel();
      const marks = (byCell.get(i) ?? []).map(({ line, msg }) => {
        const l = Math.min(line, model.getLineCount());
        return { severity: monaco.MarkerSeverity.Error, message: msg, startLineNumber: l, startColumn: model.getLineFirstNonWhitespaceColumn(l) || 1, endLineNumber: l, endColumn: model.getLineMaxColumn(l) };
      });
      monaco.editor.setModelMarkers(model, "rupy", marks);
    });
  }
}
