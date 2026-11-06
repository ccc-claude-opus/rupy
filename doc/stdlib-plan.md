# 標準函數庫與外部套件的方針

狀態：方針已定（2026-11-06），尚未實作。

## 決定

1. **系統標準函數庫：原生實作。** 在 Rust 後端和 wasm 後端都能用，也能在瀏覽器裡執行。
2. **外部套件：暫時不原生實作，改用 Python 橋接。** 寫一個第一行是 `# python: MODULE` 的 stub，或用 `rupy stub --python MODULE` 自動產生，就能呼叫真的套件。適用的套件如 pandas、scipy、sympy、requests、networkx、Pillow。
   - 限制：執行的機器要裝 Python 和那些套件；wasm 與瀏覽器不能用；回傳 `Object` 的地方沒有型別檢查。
   - 因此 [sympy-plan.md](sympy-plan.md) 的原生實作延後。
   - rstatistics 是用 rupy 寫成的自家套件，不屬於外部套件，它的繪圖規劃 [rstatistics-graphics.md](rstatistics-graphics.md) 不受這個方針影響。

## 目前已有的標準函數庫

- 內建在翻譯器：`math`、`collections`、`heapq`、`bisect`、`itertools`、`functools`、`random`、`re`、`sys`、`time`、`json.dumps`、`os.path`。
- stub（`src/lib/`）：`os`、`sys`、`time`、`subprocess`、`shlex`、`fnmatch`、`html`。

## 待補的標準函數庫（依優先順序）

| 優先 | 模組 / 函數 | 備註 |
| --- | --- | --- |
| 1 | `math.gamma`、`lgamma`、`erf`、`erfc`、`fsum`、`atanh`、`asinh`、`acosh` | 已知缺少；rstatistics 目前自行實作這些函數 |
| 1 | `json.loads` | 目前只有 `json.dumps` |
| 2 | `csv`、`io.StringIO`、`pathlib`、`datetime`、`fractions`、`decimal`、`statistics` | 資料處理 |
| 3 | `string`、`textwrap`、`copy`、`operator`、`argparse` | 常用工具 |
| 3 | `dataclasses`、`enum` | 先確認語言層是否已支援 |
| 4 | `base64`、`hashlib`、`struct`、`urllib.parse`、`uuid` | 編碼與雜湊 |
| 4 | `glob`、`shutil`、`tempfile` | 檔案系統；wasm 上以 host 提供或不支援 |
| 5 | `logging`、`sqlite3`、`threading`、`asyncio`、`pickle` | 和靜態型別或 wasm 衝突較大，最後再評估 |

每個模組都要：

- 放進 `tests/corpus/py/std_*.py`，和 CPython 比對輸出，包含錯誤訊息。
- 在 Rust 和 wasm 兩個後端都通過。

## 語言層面的相關工作

wasm 後端還不支援產生器，也不支援把函數當值傳遞。補上之後，`map(f, xs)`、`curve(dnorm)` 這類用法才能在所有後端執行。這項工作影響面很廣，可以和第 1、2 優先的模組一起排程。

## 下週（2026-11-10 額度重置後）的工作

依序進行：

1. **wasm 支援函數當值**：閉包轉換、`call_ref`，以及頂層函數、lambda、方法、內建函數各自的轉接函數。預估我的作業時間約 1–3 小時，約佔每週額度的 10–20%。
2. **第 1 優先的標準函數**：`math.gamma`、`lgamma`、`erf`、`erfc`、`fsum`、`atanh`、`asinh`、`acosh`，以及 `json.loads`。完成後，rstatistics 可以改用這些內建函數。
3. 額度有剩時，再做第 2 優先的模組。

產生器排在之後，先做受限版：不含 `send`，`yield` 不能在 `try/finally` 裡。預估約 3–6 小時，約佔每週額度的 25–40%。
