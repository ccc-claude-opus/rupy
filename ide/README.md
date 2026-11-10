# rupy IDE

在瀏覽器裡寫、編譯、執行 rupy 的 IDE（VS Code + Colab 式），跑在 [rucloud](../../rucloud) 上。
程式在瀏覽器裡編譯（`rupy.wasm`，rupy 編譯器本身編成的 WebAssembly）並執行（`rupy_wasm.mjs`），伺服器只提供靜態檔案。

```sh
sh ide/build.sh              # 建置 web/ 的 wasm（cargo + wasm32-unknown-unknown），複製到 ide/public/rupy/
sh ide/build.sh --skip-cargo # 直接複製 web/ 已有的 wasm
rucloud dev ide              # http://localhost:8787
```

需要支援 WasmGC 與 wasm 例外處理的瀏覽器（Chrome 119+、Firefox 120+、Safari 18.2+）。

## 目前功能（M0 + M1）

* Monaco 編輯器（從 jsdelivr 載入），Python 語法上色，深色模式跟著系統。
* 檔案存在瀏覽器的 IndexedDB；側欄可以新增、重新命名、刪除。第一次開會放入範例程式。
* 執行（Ctrl/⌘ + Enter）在 Web Worker 裡，輸出邊跑邊顯示；「停止」會結束 Worker，所以無窮迴圈也停得下來。
* 打字時另一個 Worker 會在背景編譯，把編譯錯誤標在那一行。
* 「標準輸入」分頁的文字給 `input()` 一行一行讀。

一次只編譯目前開啟的檔案；`import` 同專案的其他檔案要等 M4。

## 結構

```mermaid
flowchart LR
  A[app.mjs] --> E[editor.mjs<br/>Monaco]
  A --> F[fs.mjs<br/>IndexedDB]
  A --> R[runner.mjs]
  R -- postMessage --> W[runner.worker.mjs]
  W --> C[rupy/rupy.wasm<br/>編譯器]
  W --> H[rupy/rupy_wasm.mjs<br/>執行環境]
  H --> L[rupy/rupy_lib.wasm<br/>numpy 等]
  S[src/worker.js<br/>/api/*] -.M3.-> D[(D1 / R2)]
```

| 檔案 | 用途 |
|---|---|
| `wrangler.jsonc` | rucloud 設定：`public/` 靜態檔案，`/api/*` 交給 `src/worker.js` |
| `src/worker.js` | API（目前只有 `/api/health`；M3 起帳號與雲端存檔） |
| `public/app.mjs` | 介面：檔案、編輯器、執行、輸出 |
| `public/runner.mjs`、`public/runner.worker.mjs` | 在 Web Worker 編譯與執行，停止時結束 Worker |
| `public/fs.mjs` | IndexedDB 檔案存取 |
| `public/editor.mjs` | 載入 Monaco |
| `public/examples.mjs` | 範例程式（取自 `web/playground.mjs`） |

後續的里程碑見 [doc/ide-plan.md](../doc/ide-plan.md)。
