# rupy IDE 計畫

在 rucloud 上執行、類似 VS Code + Colab 的 rupy 開發環境。程式碼在 [ide/](../ide/README.md)。

## 決定

| 問題 | 決定 |
|---|---|
| 放在哪裡 | `rupy/ide/` |
| 編輯器 | Monaco |
| Notebook 語意 | 前綴重跑（見下） |
| 帳號與雲端存檔 | 先純本機（IndexedDB），M3 再加 |
| 平台 | 只要在 rucloud 上跑 |
| 協作、AI 助手 | 一開始不需要，規劃在 M6 |

## 架構

* **程式在瀏覽器裡編譯與執行。** `rupy.wasm` 編譯，`rupy_wasm.mjs` 執行，都放在 Web Worker 裡，停止時結束 Worker。伺服器只負責靜態檔案、帳號、存檔與分享。
* **Notebook 用前綴重跑。** rupy 整支程式一起編譯，沒有 REPL 狀態。執行第 $k$ 格時，把第 $1..k$ 格接成一支程式編譯執行；格與格之間插入標記，用來切開各格的輸出，錯誤行號依每格的起始行換算回各格。
* **儲存（M3）。** D1 存使用者、檔案的版本與分享連結；R2 存檔案內容與分享快照；Durable Objects 留給 M6 的即時協作。前端先寫 IndexedDB，再同步到伺服器。登入狀態用 HMAC 簽章的 cookie，不需要 KV。每個帳號是一個工作區（路徑可以有 `/`），還沒有多專案。
* **格式。** Notebook 用 nbformat 4 的 `.ipynb`，可以和 Jupyter、Colab 互相匯入匯出。

## 里程碑

| 階段 | 內容 | 狀態 |
|---|---|---|
| M0 | `ide/build.sh`、`rucloud dev ide`；在 Web Worker 執行，可停止 | ✓ |
| M1 | Monaco、檔案樹（IndexedDB）、執行與停止、輸出面板、打字時標出編譯錯誤 | ✓ |
| M2 | Notebook：程式格與 Markdown 格（含 TeX）、前綴重跑、每格輸出、匯入匯出 `.ipynb` | ✓ |
| M3 | 帳號（照 rucloud `examples/app-builder` 的 PBKDF2 + HMAC cookie）、自動存到 D1 + R2、唯讀分享連結 | ✓ |
| M4 | 多檔專案：`examples/rupy_wasm.rs` 接受一組虛擬檔案（`import` 同專案的模組）、錯誤以 JSON 回傳檔案與行號（rupy 的錯誤沒有欄號） | ✓ |
| M5 | 豐富輸出：印出的 SVG（rstatistics 的 `g.svg()`）顯示成圖並存進筆記本；wasm 後端支援 `open()`，程式可以讀寫工作區的檔案（`g.save("x.svg")`），`.svg` 檔開啟時顯示圖 | ✓ |
| M6 | Durable Objects 即時協作、AI 助手（Workers AI / AI Gateway） | |

## 風險

* **子集限制。** 一般 Python 寫法常被拒絕；wasm 後端還沒有 generator、`random`、`re`、`itertools` 等，和 Colab 的經驗差距大。
* **前綴重跑的成本。** 前面的格子每次都要重算；真正保留狀態要改 rupy 核心。
* **互動式 `input()`。** 同步等待輸入需要 SharedArrayBuffer + Atomics，也就需要 COOP/COEP 標頭，會影響從 CDN 載入 Monaco；目前用預先填好的「標準輸入」。
* **瀏覽器版本。** 需要 WasmGC 與 wasm 例外處理。
* **下載量。** 約 7.6 MB 的 wasm 加上 Monaco；之後要用雜湊檔名與長期快取。
