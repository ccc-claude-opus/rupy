# 標準函數庫與外部套件的方針

狀態（2026-11-14）：方針已定。wasm 已支援函數當值與產生器。「待補」表第 1 優先已完成（math 的 8 個函數與 `json.loads`），第 2 優先以後還沒做（`dataclasses` 已可使用）。

## 決定

1. **系統標準函數庫：原生實作。** 在 Rust 後端和 wasm 後端都能用，也能在瀏覽器裡執行。
2. **外部套件：暫時不原生實作，改用 Python 橋接。** 寫一個第一行是 `# python: MODULE` 的 stub，或用 `rupy stub --python MODULE` 自動產生，就能呼叫真的套件。適用的套件如 pandas、scipy、sympy、requests、networkx、Pillow。
   - 限制：執行的機器要裝 Python 和那些套件；wasm 與瀏覽器不能用；回傳 `Object` 的地方沒有型別檢查。
   - 因此 [sympy-plan.md](sympy-plan.md) 的原生實作延後。
   - rstatistics 是用 rupy 寫成的自家套件，不屬於外部套件，它的繪圖規劃 [rstatistics-graphics.md](rstatistics-graphics.md) 不受這個方針影響。

## 目前已有的標準函數庫

- 內建在翻譯器：`math`（含 `gamma`、`lgamma`、`erf`、`erfc`、`fsum`、`asinh`、`acosh`、`atanh`）、`collections`、`heapq`、`bisect`、`itertools`、`functools`、`random`、`re`、`sys`、`time`、`json.dumps`、`json.loads`、`os.path`。
- stub（`src/lib/`）：`os`、`sys`、`time`、`subprocess`、`shlex`、`fnmatch`、`html`。

## 待補的標準函數庫（依優先順序）

| 優先 | 模組 / 函數 | 備註 |
| --- | --- | --- |
| 1 | ~~`math.gamma`、`lgamma`、`erf`、`erfc`、`fsum`、`atanh`、`asinh`、`acosh`~~ | 已完成（2026-11-14），見下方說明 |
| 1 | ~~`json.loads`~~ | 已完成（2026-11-14），見下方說明 |
| 2 | `csv`、`io.StringIO`、`pathlib`、`datetime`、`fractions`、`decimal`、`statistics` | 資料處理 |
| 3 | `string`、`textwrap`、`copy`、`operator`、`argparse` | 常用工具 |
| 3 | `enum`（`dataclasses` 已可使用） | |
| 4 | `base64`、`hashlib`、`struct`、`urllib.parse`、`uuid` | 編碼與雜湊 |
| 4 | `glob`、`shutil`、`tempfile` | 檔案系統；wasm 上以 host 提供或不支援 |
| 5 | `logging`、`sqlite3`、`threading`、`asyncio`、`pickle` | 和靜態型別或 wasm 衝突較大，最後再評估 |

### 第 1 優先的做法與限制（2026-11-14）

- `math.gamma`、`lgamma`：照搬 CPython 的 Lanczos 程式。CPython 在 macOS arm64 上由 clang 編譯，`a * b + c` 被合併成 fused multiply-add，所以 rupy 也用 FMA（Rust 用 `mul_add`，wasm 用 BigInt 做的 `fmaExact`）。不用 FMA 時，4 萬個測試值中有 8,525 個差 1 ulp；用了之後全部相同。
- `erf`、`erfc`、`asinh`、`acosh`、`atanh`：Rust 後端呼叫 C 函式庫，和 CPython 用的是同一份，所以結果逐位元相同。
- wasm 後端：`erf`、`erfc` 用 FreeBSD 的演算法，`exp`、`pow` 用 JavaScript 的，最後一位數可能和 CPython 不同（原本的 `math.exp` 也是如此）。因此 `tests/corpus/py/std_math_special.py` 只在 Rust 後端比對全部位數；`std_math_special12.py` 在兩個後端比對 12 位有效數字與錯誤訊息。
- `math.fsum`：Shewchuk 演算法，和 CPython 的捨入方式相同，兩個後端都逐位元相同（`std_math_fsum.py`）。
- `json.loads`：結果的型別由宣告決定，例如 `xs: list[int] = json.loads(s)`。可用的型別是 int、float、str、bool、`Optional`，以及由它們組成的 `list` 和 `dict[str, ...]`。
  - 沒有宣告型別、或宣告了 tuple 等型別時，編譯時就拒絕（`tests/corpus/err/json_loads_*.py`）。
  - JSON 的型別和宣告不合時，丟出 TypeError。例如宣告 float 卻讀到 `1`：CPython 會保留 int，印出來是 `1` 而不是 `1.0`，為了不產生和 CPython 不同的結果，rupy 直接報錯。
  - 型別混雜的 JSON 請用 `rupy.json.Json`。
  - 解析錯誤是 ValueError，訊息和 CPython 相同。CPython 實際丟出的是它的子類別 `json.JSONDecodeError`，所以沒有被攔截時，traceback 印出的類別名稱不同。

每個模組都要：

- 放進 `tests/corpus/py/std_*.py`，和 CPython 比對輸出，包含錯誤訊息。
- 在 Rust 和 wasm 兩個後端都通過。

## 語言層面的相關工作

已完成（2026-11）：wasm 後端支援產生器（包含 `try` 裡的 `yield`）、函數當值、`nonlocal`、`functools.cache`；Rust 後端也支援函數當值。

## 2026-11-10 那週的工作

第 1、2 項已完成（第 1 項由其他 AI 完成，產生器也一併做了）；第 3 項還沒做。原訂順序：

1. **wasm 支援函數當值**：閉包轉換、`call_ref`，以及頂層函數、lambda、方法、內建函數各自的轉接函數。預估我的作業時間約 1–3 小時，約佔每週額度的 10–20%。
2. **第 1 優先的標準函數**：`math.gamma`、`lgamma`、`erf`、`erfc`、`fsum`、`atanh`、`asinh`、`acosh`，以及 `json.loads`。已完成。rstatistics 不改用它們：rstatistics 要和 R 的數字一致，R 的 `lgammafn` 等函數和 CPython 的演算法不同，所以保留 rstatistics 自己照 R 寫的版本。
3. 額度有剩時，再做第 2 優先的模組。

產生器排在之後，先做受限版：不含 `send`，`yield` 不能在 `try/finally` 裡。預估約 3–6 小時，約佔每週額度的 25–40%。
