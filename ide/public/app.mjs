// The rupy IDE: files in IndexedDB (fs.mjs), Monaco (editor.mjs), and two
// workers (runner.mjs): one runs programs, one compiles as you type to mark errors.
import { openFs } from "./fs.mjs";
import { loadMonaco, darkQuery, themeName } from "./editor.mjs";
import { Runner, errorLines } from "./runner.mjs";
import { EXAMPLES } from "./examples.mjs";

const $ = (id) => document.getElementById(id);
const runBtn = $("run"), stopBtn = $("stop"), status = $("status"), output = $("output"), stdin = $("stdin");

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

const editor = monaco.editor.create($("editor"), {
  automaticLayout: true,
  fontSize: 13,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  tabSize: 4,
  insertSpaces: true,
});

// ------------------------------------------------------------------ files

const models = new Map(); // path → model
let current = null;

function modelFor(path, text) {
  let m = models.get(path);
  if (!m) {
    m = monaco.editor.createModel(text, "python", monaco.Uri.file(path));
    models.set(path, m);
    let timer;
    m.onDidChangeContent(() => {
      clearTimeout(timer);
      timer = setTimeout(() => fs.put(path, m.getValue()), 400);
      scheduleCheck();
    });
  }
  return m;
}

async function renderFiles() {
  const ul = $("files");
  ul.replaceChildren();
  for (const f of await fs.list()) {
    const li = document.createElement("li");
    li.className = f.path === current ? "active" : "";
    li.title = f.path;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = f.path;
    const ren = actButton("✎", "重新命名", () => renameFile(f.path));
    const del = actButton("✕", "刪除", () => deleteFile(f.path));
    li.append(name, ren, del);
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

async function openFile(path) {
  const f = await fs.get(path);
  if (!f) return;
  current = path;
  store.set("current", path);
  editor.setModel(modelFor(path, f.text));
  $("current").textContent = path;
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
  const name = askName("新檔案的名稱", "main.py");
  if (!name) return;
  if (await fs.get(name)) return alert(name + " 已經存在");
  await fs.put(name, "");
  await openFile(name);
};

async function renameFile(path) {
  const name = askName("新的名稱", path);
  if (!name || name === path) return;
  if (await fs.get(name)) return alert(name + " 已經存在");
  const text = models.get(path)?.getValue() ?? (await fs.get(path)).text;
  await fs.put(name, text);
  await fs.remove(path);
  models.get(path)?.dispose();
  models.delete(path);
  await (current === path ? openFile(name) : renderFiles());
}

async function deleteFile(path) {
  if (!confirm(`刪除 ${path}？（無法復原）`)) return;
  await fs.remove(path);
  models.get(path)?.dispose();
  models.delete(path);
  if (current === path) {
    current = null;
    const rest = await fs.list();
    if (rest.length) return openFile(rest[0].path);
    editor.setModel(null);
    $("current").textContent = "—";
  }
  await renderFiles();
}

// ------------------------------------------------------- errors as you type

const checker = new Runner();
let checkTimer, checkSeq = 0;

function scheduleCheck(delay = 600) {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(check, delay);
}

async function check() {
  const model = editor.getModel();
  if (!model) return;
  const seq = ++checkSeq;
  if (checker.busy) checker.stop(); // a compile that takes too long: start over
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

async function go() {
  const model = editor.getModel();
  if (!model || runner.busy) return;
  showPane("output");
  output.replaceChildren();
  runBtn.disabled = true;
  stopBtn.disabled = false;
  status.textContent = `${current} 執行中…`;
  const r = await runner.request("run", model.getValue(), {
    stdin: stdin.value,
    onOutput: (fd, text) => append(text, fd === 2 ? "stderr" : ""),
  });
  runBtn.disabled = false;
  stopBtn.disabled = true;
  if (r.stopped) {
    append("\n[已停止]\n", "stderr");
    status.textContent = `${current}：已停止`;
  } else if (r.error) {
    append(r.error + "\n", "stderr");
    monaco.editor.setModelMarkers(model, "rupy", markers(model, r.error));
    status.textContent = `編譯錯誤（${r.compileMs.toFixed(0)} ms）`;
  } else {
    status.textContent = `編譯 ${r.compileMs.toFixed(0)} ms（${r.bytes} bytes）· 執行 ${r.runMs.toFixed(0)} ms · 結束碼 ${r.code}`;
  }
}

runBtn.onclick = go;
stopBtn.onclick = () => runner.stop();
$("clear").onclick = () => output.replaceChildren();
editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, go);

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

// ------------------------------------------------------------------ start

const files = await fs.list();
const start = files.find((f) => f.path === store.get("current")) ?? files[0];
if (start) await openFile(start.path);
else await renderFiles();
await runner.ready;
runBtn.disabled = false;
status.textContent = "就緒（Ctrl/⌘ + Enter 執行）";
