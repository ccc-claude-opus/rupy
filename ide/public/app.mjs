// The rupy IDE: files in IndexedDB (fs.mjs), Monaco (editor.mjs), notebooks
// (notebook.mjs) and two workers (runner.mjs): one runs programs, one compiles
// as you type to mark errors.
import { openFs } from "./fs.mjs";
import { loadMonaco, darkQuery, themeName } from "./editor.mjs";
import { Runner, errorLines } from "./runner.mjs";
import { NotebookView } from "./notebook.mjs";
import { parseNotebook, serializeNotebook, newCell } from "./nbformat.mjs";
import { EXAMPLES, NOTEBOOK } from "./examples.mjs";

const $ = (id) => document.getElementById(id);
const runBtn = $("run"), runAllBtn = $("run-all"), stopBtn = $("stop"), status = $("status"), output = $("output"), stdin = $("stdin");
const editorEl = $("editor"), notebookEl = $("notebook");

const store = {
  get(k) {
    try {
      return localStorage.getItem("rupy-ide." + k);
    } catch {
      return null;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem("rupy-ide." + k, v);
    } catch {}
  },
};

const fs = await openFs();
if (!fs.persistent) $("storage-note").textContent = "這個瀏覽器不能用 IndexedDB，檔案只存在這個分頁。";
if ((await fs.list()).length === 0) {
  // `_demo`: a numpy.py would hide numpy under CPython
  for (const [name, text] of Object.entries(EXAMPLES)) await fs.put(name.toLowerCase() + "_demo.py", text);
  await fs.put("intro.ipynb", serializeNotebook(NOTEBOOK));
}

let monaco;
try {
  monaco = await loadMonaco();
} catch (e) {
  status.textContent = "編輯器載入失敗：" + e.message;
  throw e;
}
monaco.editor.setTheme(themeName());
darkQuery.addEventListener("change", () => monaco.editor.setTheme(themeName()));

const editor = monaco.editor.create(editorEl, {
  automaticLayout: true,
  fontSize: 13,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  tabSize: 4,
  insertSpaces: true,
});

// ------------------------------------------------------------------ files

const models = new Map(); // path → model of a program file
let current = null;
let view = null; // the NotebookView when a notebook is open

// saving waits 400 ms after the last change; switching files saves at once
let pendingSave = null;
function saveLater(path, text) {
  clearTimeout(pendingSave?.timer);
  pendingSave = { path, text, timer: setTimeout(flushSave, 400) };
}
async function flushSave() {
  const p = pendingSave;
  if (!p) return;
  pendingSave = null;
  clearTimeout(p.timer);
  await fs.put(p.path, p.text());
}

function modelFor(path, text) {
  let m = models.get(path);
  if (!m) {
    m = monaco.editor.createModel(text, "python", monaco.Uri.file(path));
    models.set(path, m);
    m.onDidChangeContent(() => {
      saveLater(path, () => m.getValue());
      scheduleCheck();
    });
  }
  return m;
}

const isNotebook = (path) => path.endsWith(".ipynb");

async function renderFiles() {
  const ul = $("files");
  ul.replaceChildren();
  for (const f of await fs.list()) {
    const li = document.createElement("li");
    li.className = f.path === current ? "active" : "";
    li.title = f.path;
    const icon = document.createElement("span");
    icon.className = "icon";
    icon.textContent = isNotebook(f.path) ? "▤" : "•";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = f.path;
    const ren = actButton("✎", "重新命名", () => renameFile(f.path));
    const del = actButton("✕", "刪除", () => deleteFile(f.path));
    li.append(icon, name, ren, del);
    li.onclick = () => openFile(f.path);
    ul.append(li);
  }
}

function actButton(label, title, fn) {
  const b = document.createElement("button");
  b.className = "act";
  b.textContent = label;
  b.title = title;
  b.setAttribute("aria-label", title);
  b.onclick = (e) => {
    e.stopPropagation();
    fn();
  };
  return b;
}

function closeView() {
  view?.dispose();
  view = null;
  notebookEl.hidden = true;
  editorEl.hidden = false;
  runAllBtn.hidden = true;
  $("output-tab").hidden = $("clear").hidden = false;
  document.querySelector(".layout").classList.remove("nb");
}

async function openFile(path) {
  if (runner.busy) runner.stop();
  await flushSave();
  const f = await fs.get(path);
  if (!f) return;
  closeView();
  current = path;
  store.set("current", path);
  $("current").textContent = path;
  if (isNotebook(path)) {
    editor.setModel(null);
    editorEl.hidden = true;
    notebookEl.hidden = false;
    runAllBtn.hidden = false;
    $("output-tab").hidden = $("clear").hidden = true; // a notebook's output is under its cells
    document.querySelector(".layout").classList.add("nb");
    showPane("stdin");
    const v = new NotebookView(notebookEl, {
      monaco,
      runner,
      stdin: () => stdin.value,
      onChange: () => saveLater(path, () => v.text()),
      onEdit: () => scheduleCheck(),
      onRunRequest: (upto) => go(upto),
    });
    try {
      v.load(f.text);
      view = v;
    } catch (e) {
      v.dispose();
      notebookEl.textContent = `無法讀取 ${path}：${e.message}`;
    }
  } else {
    editor.setModel(modelFor(path, f.text));
  }
  await renderFiles();
  scheduleCheck(0);
}

function askName(message, initial) {
  let name = prompt(message, initial)?.trim();
  if (!name) return null;
  if (!/\.\w+$/.test(name)) name += ".py";
  if (!/^[\w.\-/]+$/.test(name)) {
    alert("檔名只能用英數字、底線、點、減號和 /");
    return null;
  }
  return name;
}

$("new-file").onclick = async () => {
  const name = askName("新檔案的名稱（.py 程式，或 .ipynb 筆記本）", "main.py");
  if (!name) return;
  if (await fs.get(name)) return alert(name + " 已經存在");
  await fs.put(name, isNotebook(name) ? serializeNotebook({ cells: [newCell()] }) : "");
  await openFile(name);
};

async function renameFile(path) {
  const name = askName("新的名稱", path);
  if (!name || name === path) return;
  if (await fs.get(name)) return alert(name + " 已經存在");
  if (isNotebook(name) !== isNotebook(path)) return alert("不能在程式和筆記本之間改副檔名");
  await flushSave();
  await fs.put(name, (await fs.get(path)).text);
  await fs.remove(path);
  models.get(path)?.dispose();
  models.delete(path);
  await (current === path ? openFile(name) : renderFiles());
}

async function deleteFile(path) {
  if (!confirm(`刪除 ${path}？（無法復原）`)) return;
  if (pendingSave?.path === path) {
    clearTimeout(pendingSave.timer);
    pendingSave = null;
  }
  await fs.remove(path);
  models.get(path)?.dispose();
  models.delete(path);
  if (current === path) {
    current = null;
    closeView();
    const rest = await fs.list();
    if (rest.length) return openFile(rest[0].path);
    editor.setModel(null);
    $("current").textContent = "—";
  }
  await renderFiles();
}

// import .py / .ipynb files; download the open one
const picker = $("import-input");
$("import").onclick = () => picker.click();
picker.onchange = async () => {
  let last = null;
  for (const file of picker.files) {
    const text = await file.text();
    if (isNotebook(file.name)) {
      try {
        parseNotebook(text);
      } catch (e) {
        alert(`${file.name} 不是筆記本：${e.message}`);
        continue;
      }
    }
    let name = file.name.replace(/[^\w.\-]/g, "_");
    for (let n = 1; await fs.get(name); n++) name = file.name.replace(/[^\w.\-]/g, "_").replace(/(\.\w+)?$/, `-${n}$1`);
    await fs.put(name, text);
    last = name;
  }
  picker.value = "";
  if (last) await openFile(last);
};

$("download").onclick = async () => {
  if (!current) return;
  await flushSave();
  const text = view ? view.text() : editor.getValue();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: isNotebook(current) ? "application/x-ipynb+json" : "text/x-python" }));
  a.download = current.split("/").pop();
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};

// ------------------------------------------------------- errors as you type

const checker = new Runner();
let checkTimer, checkSeq = 0;

function scheduleCheck(delay = 600) {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(check, delay);
}

async function check() {
  const seq = ++checkSeq;
  if (checker.busy) checker.stop(); // a compile that takes too long: start over
  if (view) return view.check(checker);
  const model = editor.getModel();
  if (!model) return;
  const r = await checker.request("compile", model.getValue());
  if (seq !== checkSeq || r.stopped || model.isDisposed()) return;
  monaco.editor.setModelMarkers(model, "rupy", markers(model, r.error));
}

function markers(model, error) {
  if (!error) return [];
  const found = errorLines(error).filter((e) => e.file === null);
  if (!found.length) return [{ severity: monaco.MarkerSeverity.Error, message: error, startLineNumber: 1, startColumn: 1, endLineNumber: 1, endColumn: 1 }];
  return found.map(({ line, msg }) => {
    const l = Math.min(Math.max(line, 1), model.getLineCount());
    return { severity: monaco.MarkerSeverity.Error, message: msg, startLineNumber: l, startColumn: model.getLineFirstNonWhitespaceColumn(l) || 1, endLineNumber: l, endColumn: model.getLineMaxColumn(l) };
  });
}

// -------------------------------------------------------------------- run

const runner = new Runner();

function append(text, cls) {
  const last = output.lastChild;
  if (last && last.className === (cls ?? "")) last.textContent += text;
  else {
    const span = document.createElement("span");
    span.className = cls ?? "";
    span.textContent = text;
    output.append(span);
  }
  output.scrollTop = output.scrollHeight;
}

/** Run the open program, or the notebook's cells 0..upto (default: the active cell). */
async function go(upto) {
  if (runner.busy || !current) return;
  runBtn.disabled = runAllBtn.disabled = true;
  stopBtn.disabled = false;
  status.textContent = `${current} 執行中…`;
  let r;
  if (view) {
    r = await view.run(typeof upto === "number" ? upto : view.activeIndex());
  } else {
    const model = editor.getModel();
    showPane("output");
    output.replaceChildren();
    r = await runner.request("run", model.getValue(), {
      stdin: stdin.value,
      onOutput: (fd, text) => append(text, fd === 2 ? "stderr" : ""),
    });
    if (r.stopped) append("\n[已停止]\n", "stderr");
    else if (r.error) {
      append(r.error + "\n", "stderr");
      monaco.editor.setModelMarkers(model, "rupy", markers(model, r.error));
    }
  }
  runBtn.disabled = runAllBtn.disabled = false;
  stopBtn.disabled = true;
  const cells = view ? `${r.cells} 格 · ` : "";
  if (r.stopped) status.textContent = `${current}：已停止`;
  else if (r.error) status.textContent = `編譯錯誤（${r.compileMs.toFixed(0)} ms）`;
  else status.textContent = `${cells}編譯 ${r.compileMs.toFixed(0)} ms（${r.bytes} bytes）· 執行 ${r.runMs.toFixed(0)} ms · 結束碼 ${r.code}`;
}

runBtn.onclick = () => go();
runAllBtn.onclick = () => go(Infinity);
stopBtn.onclick = () => runner.stop();
$("clear").onclick = () => output.replaceChildren();
editor.addAction({ id: "rupy.run", label: "執行", keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter], run: () => go() });

// ----------------------------------------------------------- output tabs

function showPane(name) {
  for (const tab of document.querySelectorAll(".panel-tabs [role=tab]")) {
    const on = tab.dataset.pane === name;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", on);
  }
  output.hidden = name !== "output";
  stdin.hidden = name !== "stdin";
}
for (const tab of document.querySelectorAll(".panel-tabs [role=tab]")) tab.onclick = () => showPane(tab.dataset.pane);
stdin.value = store.get("stdin") ?? "";
stdin.oninput = () => store.set("stdin", stdin.value);
addEventListener("beforeunload", () => {
  if (pendingSave) flushSave();
});

// ------------------------------------------------------------------ start

const files = await fs.list();
const start = files.find((f) => f.path === store.get("current")) ?? files[0];
if (start) await openFile(start.path);
else await renderFiles();
await runner.ready;
runBtn.disabled = runAllBtn.disabled = false;
status.textContent = "就緒（Ctrl/⌘ + Enter 執行）";
