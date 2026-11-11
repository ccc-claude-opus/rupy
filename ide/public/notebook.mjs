// The notebook view: a Monaco editor per cell, outputs under code cells,
// rendered Markdown (double-click to edit). Running cell k runs code cells
// 0..k as one program (nbformat.mjs) and splits the output among them.
import { parseNotebook, serializeNotebook, buildProgram, locate, outputSplitter, newCell } from "./nbformat.mjs";
import { richSplitter, outputNode, isImage } from "./rich.mjs";
import { formatError, markerMessage } from "./runner.mjs";

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
    item.out.replaceChildren(...item.cell.outputs.map(outputNode));
    item.out.hidden = item.cell.outputs.length === 0;
    item.countEl.textContent = item.cell.count ? `[${item.cell.count}]` : "[ ]";
  }

  appendOutput(i, name, text) {
    const item = this.items[i];
    if (!item?.out || !text) return;
    const outs = item.cell.outputs;
    const last = outs[outs.length - 1];
    if (last && last.name === name && !isImage(last)) {
      last.text += text;
      item.out.lastChild.textContent += text;
    } else {
      const o = { name, text };
      outs.push(o);
      item.out.append(outputNode(o));
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
    const rich = new Map(); // cell → its richSplitter: the pictures in its output
    const split = outputSplitter((i, text) => {
      if (started[started.length - 1] !== i) {
        const prev = started[started.length - 1];
        this.items[prev]?.el.classList.remove("running");
        rich.get(prev)?.flush();
        started.push(i);
        this.items[i].el.classList.replace("queued", "running");
        rich.set(i, richSplitter((kind, s) => this.appendOutput(i, kind === "svg" ? "svg" : "stdout", s)));
      }
      rich.get(i).feed(text);
    });
    const project = await this.opts.project(src);
    const r = ran.length
      ? await runner.request("run", project, {
          stdin: this.opts.stdin(),
          onFile: this.opts.onFile,
          onOutput: (fd, text) => (fd === 1 ? split.feed(text) : this.appendOutput(split.current >= 0 ? split.current : ran[0], "stderr", text)),
        })
      : { type: "done", code: 0, compileMs: 0, runMs: 0, bytes: 0 };
    for (const r of rich.values()) r.flush();
    if (r.error) this.showCompileError(r.error, starts, project.main);
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

  /** Where an error is: { cell, line } in this notebook, or null (another file, or no line). */
  where(error, starts, main) {
    return error.file === main && error.line ? locate(starts, error.line) : null;
  }

  showCompileError(error, starts, main) {
    const at = this.where(error, starts, main);
    if (at) this.appendOutput(at.cell, "stderr", `第 ${at.line} 行：${error.msg}${error.hint ? `\n  提示：${error.hint}` : ""}\n`);
    else this.appendOutput(starts[starts.length - 1]?.cell ?? 0, "stderr", formatError(error.file === main ? { ...error, file: "筆記本" } : error) + "\n");
    this.setMarkers(error, starts, main);
  }

  // ---------------------------------------------------- errors as you type

  /** Compile every code cell with `checker`; mark the errors in their cells. */
  async check(checker) {
    const { src, starts } = buildProgram(this.nb.cells);
    const project = await this.opts.project(src);
    const r = await checker.request("compile", project);
    if (r.stopped || !this.items.length) return false;
    this.setMarkers(r.error, starts, project.main);
    return true;
  }

  /** Mark `error` (null: none) in its cell; an error in another file is marked
   *  there (opts.markOther) and, as a warning, on the first code cell. */
  setMarkers(error, starts, main) {
    const { monaco } = this.opts;
    const at = error && this.where(error, starts, main);
    const other = error && !at && error.file !== main ? error : null;
    this.opts.markOther?.(other);
    const first = this.items.findIndex((it) => it.cell.type === "code");
    this.items.forEach((it, i) => {
      if (it.cell.type !== "code") return;
      const model = it.editor.getModel();
      const marks = [];
      if (at && at.cell === i) marks.push(lineMarker(monaco, model, at.line, markerMessage(error), monaco.MarkerSeverity.Error));
      else if (error && !at && i === first) marks.push(lineMarker(monaco, model, 1, other ? `${error.file} 第 ${error.line} 行有錯誤：${markerMessage(error)}` : markerMessage(error), other ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Error));
      monaco.editor.setModelMarkers(model, "rupy", marks);
    });
  }
}

/** A marker over line `line` of `model`. */
export function lineMarker(monaco, model, line, message, severity) {
  const l = Math.min(Math.max(line, 1), model.getLineCount());
  return { severity, message, startLineNumber: l, startColumn: model.getLineFirstNonWhitespaceColumn(l) || 1, endLineNumber: l, endColumn: model.getLineMaxColumn(l) };
}
