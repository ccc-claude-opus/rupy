// Monaco (VS Code's editor) from jsdelivr, one model per file.
const VERSION = "0.52.2";
const BASE = `https://cdn.jsdelivr.net/npm/monaco-editor@${VERSION}/min`;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error("could not load " + src));
    document.head.append(s);
  });
}

export async function loadMonaco() {
  // the editor's web worker, from the CDN through a same-origin data: URL
  window.MonacoEnvironment = {
    getWorkerUrl: () =>
      "data:text/javascript;charset=utf-8," +
      encodeURIComponent(`self.MonacoEnvironment={baseUrl:'${BASE}/'};importScripts('${BASE}/vs/base/worker/workerMain.js');`),
  };
  await loadScript(`${BASE}/vs/loader.js`);
  window.require.config({ paths: { vs: `${BASE}/vs` } });
  return new Promise((resolve, reject) => window.require(["vs/editor/editor.main"], () => resolve(window.monaco), reject));
}

export const darkQuery = matchMedia("(prefers-color-scheme: dark)");
export const themeName = () => (darkQuery.matches ? "vs-dark" : "vs");
