// The rupy IDE: files in IndexedDB (fs.mjs), kept in step with the account's
// files on the server (sync.mjs) when signed in; Monaco (editor.mjs), notebooks
// (notebook.mjs) and two workers (runner.mjs): one runs programs, one compiles
// as you type to mark errors.
import { openFs, dbName, deleteFs } from "./fs.mjs";
import { Sync, api } from "./sync.mjs";
import { loadMonaco, darkQuery, themeName } from "./editor.mjs";
import { Runner, formatError, markerMessage } from "./runner.mjs";
import { NotebookView, lineMarker } from "./notebook.mjs";
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

// the account: { accounts: whether the server has them, user: { id, email } | null }
let me = { accounts: false, user: null };
try {
  me = (await api("/api/me")).data;
} catch {}
const user = me.user;
let sync = null;
const fs = await openFs(dbName(user?.id), { onWrite: () => sync?.schedule() });
if (!fs.persistent) $("storage-note").textContent = "這個瀏覽器不能用 IndexedDB，檔案只存在這個分頁。";

// the examples of a new workspace (not signed in); `_demo`: a numpy.py would hide numpy under CPython
const SEEDS = new Map([...Object.entries(EXAMPLES).map(([name, text]) => [name.toLowerCase() + "_demo.py", text]), ["intro.ipynb", serializeNotebook(NOTEBOOK)]]);
if (!user && (await fs.list()).length === 0) for (const [path, text] of SEEDS) await fs.put(path, text);
const CURRENT = "current." + dbName(user?.id);

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
let applyingRemote = false; // a model takes the server's text: not an edit
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
      if (applyingRemote) return;
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
    li.append(icon, name);
    if (user) li.append(actButton("⇪", "分享唯讀連結", () => shareFile(f.path)));
    li.append(ren, del);
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
  store.set(CURRENT, path);
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
      project: (src) => project(path + ".py", src), // the notebook's program, next to the modules
      markOther,
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
    const name = await uniqueName(file.name);
    await fs.put(name, text);
    last = name;
  }
  picker.value = "";
  if (last) await openFile(last);
};

/** `name` with only the characters a path may have, and -1, -2 … until no file has it. */
async function uniqueName(name) {
  name = name.replace(/[^\w.\-]/g, "_");
  let out = name;
  for (let n = 1; await fs.get(out); n++) out = name.replace(/(\.\w+)?$/, `-${n}$1`);
  return out;
}

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
  const main = current;
  const r = await checker.request("compile", await project(main));
  if (seq !== checkSeq || r.stopped || model.isDisposed()) return;
  showErrors(model, main, r.error);
}

/** The workspace's programs ({ path: text }), with the open editors' text. */
async function projectFiles() {
  const files = {};
  for (const f of await fs.list()) if (f.path.endsWith(".py")) files[f.path] = f.text;
  for (const [p, m] of models) if (!m.isDisposed()) files[p] = m.getValue();
  return files;
}

/** What the compiler gets: `main` and every program of the workspace (the modules it may import). */
async function project(main, text) {
  const files = await projectFiles();
  if (text !== undefined) files[main] = text;
  return { main, files };
}

// an error in a module is marked in it too (when it has an editor model)
let markedOther = null;
function markOther(error) {
  const old = markedOther && models.get(markedOther);
  if (old && !old.isDisposed()) monaco.editor.setModelMarkers(old, "rupy", []);
  markedOther = null;
  const m = error?.line ? models.get(error.file) : null;
  if (!m) return;
  monaco.editor.setModelMarkers(m, "rupy", [lineMarker(monaco, m, error.line, markerMessage(error), monaco.MarkerSeverity.Error)]);
  markedOther = error.file;
}

/** Mark the error of compiling `main` (shown in `model`; null: no error). */
function showErrors(model, main, error) {
  const here = error && error.file === main;
  markOther(error && !here ? error : null);
  const marks = !error
    ? []
    : here
      ? [lineMarker(monaco, model, error.line, markerMessage(error), monaco.MarkerSeverity.Error)]
      : [lineMarker(monaco, model, 1, `${error.file}${error.line ? ` 第 ${error.line} 行` : ""}有錯誤：${markerMessage(error)}`, monaco.MarkerSeverity.Warning)];
  monaco.editor.setModelMarkers(model, "rupy", marks);
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
    const main = current;
    r = await runner.request("run", await project(main), {
      stdin: stdin.value,
      onOutput: (fd, text) => append(text, fd === 2 ? "stderr" : ""),
    });
    if (r.stopped) append("\n[已停止]\n", "stderr");
    else if (r.error) {
      append(formatError(r.error) + "\n", "stderr");
      showErrors(model, main, r.error);
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

// ---------------------------------------------------------------- account

const syncEl = $("sync"), accountBtn = $("account");
accountBtn.hidden = !me.accounts;
if (user) {
  accountBtn.textContent = user.email;
  sync = new Sync(fs, {
    before: flushSave,
    onStatus: (text, kind) => {
      syncEl.textContent = text;
      syncEl.dataset.kind = kind;
    },
    onRemote: applyRemote,
  });
}

/** The server changed these files here: reload what shows them. */
async function applyRemote(paths) {
  for (const p of paths) {
    if (p === current) continue;
    models.get(p)?.dispose();
    models.delete(p);
  }
  if (current && paths.includes(current)) {
    const f = await fs.get(current);
    if (!f) {
      current = null;
      closeView();
      const rest = await fs.list();
      if (rest.length) return openFile(rest[0].path);
      editor.setModel(null);
      $("current").textContent = "—";
    } else if (view) {
      if (!runner.busy && view.text() !== f.text) await openFile(current);
    } else {
      const m = models.get(current);
      if (m && m.getValue() !== f.text) {
        applyingRemote = true;
        m.setValue(f.text);
        applyingRemote = false;
      }
    }
  }
  await renderFiles();
}

async function shareFile(path) {
  await flushSave();
  const f = await fs.get(path);
  if (!f) return;
  try {
    const { data } = await api("/api/shares", { method: "POST", body: { path, text: f.text } });
    const url = location.origin + data.url;
    try {
      await navigator.clipboard.writeText(url);
    } catch {}
    prompt("唯讀分享連結（已複製）。這是目前內容的快照，之後的修改要再分享一次。", url);
  } catch (e) {
    alert("分享失敗：" + e.message);
  }
}

const loginDialog = $("login-dialog"), accountDialog = $("account-dialog");
accountBtn.onclick = () => (user ? openAccount() : loginDialog.showModal());

$("login-form").onsubmit = async (e) => {
  e.preventDefault();
  const action = e.submitter?.value;
  if (action === "cancel") return loginDialog.close();
  const form = new FormData(e.target);
  const body = { email: form.get("email"), password: form.get("password") };
  $("login-error").textContent = "";
  let data;
  try {
    ({ data } = await api(action === "register" ? "/api/register" : "/api/login", { method: "POST", body }));
  } catch (err) {
    $("login-error").textContent = err.message;
    return;
  }
  // this computer's own files (not the untouched examples) can go to the account
  await flushSave();
  const mine = (await fs.list()).filter((f) => SEEDS.get(f.path) !== f.text);
  if (mine.length && confirm(`要把這台電腦上的 ${mine.length} 個檔案複製到帳號嗎？（帳號裡同名的檔案會保留兩份）`)) {
    const target = await openFs(dbName(data.user.id));
    for (const f of mine) if (!(await target.get(f.path))) await target.put(f.path, f.text);
    target.close();
  }
  location.reload();
};

async function openAccount() {
  $("account-email").textContent = user.email;
  const ul = $("share-list");
  ul.replaceChildren(Object.assign(document.createElement("li"), { textContent: "載入中…" }));
  accountDialog.showModal();
  try {
    const { shares } = (await api("/api/shares")).data;
    ul.replaceChildren();
    if (!shares.length) ul.append(Object.assign(document.createElement("li"), { className: "muted", textContent: "還沒有分享連結（檔案旁的 ⇪）" }));
    for (const sh of shares) {
      const li = document.createElement("li");
      const a = Object.assign(document.createElement("a"), { href: sh.url, target: "_blank", rel: "noopener", textContent: sh.path });
      const date = Object.assign(document.createElement("span"), { className: "muted", textContent: " " + sh.created_at.slice(0, 16).replace("T", " ") });
      const del = actButton("取消分享", "取消這個分享連結", async () => {
        await api("/api/shares/" + sh.id, { method: "DELETE" });
        li.remove();
      });
      li.append(a, date, del);
      ul.append(li);
    }
  } catch (e) {
    ul.replaceChildren(Object.assign(document.createElement("li"), { textContent: "無法載入：" + e.message }));
  }
}

$("account-close").onclick = () => accountDialog.close();
$("logout").onclick = async () => {
  await sync.run();
  const dirty = (await fs.all()).filter((r) => r.dirty);
  if (dirty.length && !confirm(`還有 ${dirty.length} 個檔案沒同步到伺服器，登出後會遺失。確定登出？`)) return;
  await api("/api/logout", { method: "POST" });
  fs.close();
  await deleteFs(dbName(user.id)); // the account's files stay on the server, not on this computer
  location.reload();
};

// ------------------------------------------------------------------ start

// /#import=<share id>: a copy of a shared file
let startPath = store.get(CURRENT);
const shareId = location.hash.match(/^#import=([0-9a-f]{16})$/)?.[1];
if (shareId) {
  history.replaceState(null, "", location.pathname);
  try {
    const { data } = await api("/api/s/" + shareId);
    startPath = await uniqueName(data.path.split("/").pop());
    await fs.put(startPath, data.text);
  } catch (e) {
    alert("無法開啟分享的檔案：" + e.message);
  }
}
const files = await fs.list();
const start = files.find((f) => f.path === startPath) ?? files[0];
if (start) await openFile(start.path);
else await renderFiles();
await runner.ready;
runBtn.disabled = runAllBtn.disabled = false;
status.textContent = "就緒（Ctrl/⌘ + Enter 執行）";
sync?.schedule(0);
