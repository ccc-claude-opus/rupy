# 標準函數庫與外部套件的方針

狀態（2026-11-14）：方針已定。wasm 已支援函數當值與產生器。「待補」表第 1 優先已完成（math 的 8 個函數與 `json.loads`）；第 2 優先完成 `statistics`、`fractions`、`csv`、`io.StringIO`、`datetime`、`pathlib`，只剩 `decimal`（`dataclasses` 已可使用）。

## 決定

1. **系統標準函數庫：原生實作。** 在 Rust 後端和 wasm 後端都能用，也能在瀏覽器裡執行。
2. **外部套件：暫時不原生實作，改用 Python 橋接。** 寫一個第一行是 `# python: MODULE` 的 stub，或用 `rupy stub --python MODULE` 自動產生，就能呼叫真的套件。適用的套件如 pandas、scipy、sympy、requests、networkx、Pillow。
   - 限制：執行的機器要裝 Python 和那些套件；wasm 與瀏覽器不能用；回傳 `Object` 的地方沒有型別檢查。
   - 因此 [sympy-plan.md](sympy-plan.md) 的原生實作延後。
   - rstatistics 是用 rupy 寫成的自家套件，不屬於外部套件，它的繪圖規劃 [rstatistics-graphics.md](rstatistics-graphics.md) 不受這個方針影響。

## 目前已有的標準函數庫

- 內建在翻譯器：`math`（含 `gamma`、`lgamma`、`erf`、`erfc`、`fsum`、`asinh`、`acosh`、`atanh`）、`collections`、`heapq`、`bisect`、`itertools`、`functools`、`random`、`re`、`sys`、`time`、`json.dumps`、`json.loads`、`os.path`。
- stub（`src/lib/`）：`os`、`sys`、`time`、`subprocess`、`shlex`、`fnmatch`、`html`。
- 用 rupy 寫成（`pylib/`，和 rstatistics 一樣內建在 rupy 裡）：`statistics`、`fractions`、`csv`、`io`（`StringIO`）、`datetime`、`pathlib`。

## 待補的標準函數庫（依優先順序）

| 優先 | 模組 / 函數 | 備註 |
| --- | --- | --- |
| 1 | ~~`math.gamma`、`lgamma`、`erf`、`erfc`、`fsum`、`atanh`、`asinh`、`acosh`~~ | 已完成（2026-11-14），見下方說明 |
| 1 | ~~`json.loads`~~ | 已完成（2026-11-14），見下方說明 |
| 2 | ~~`csv`、`io.StringIO`、`fractions`、`statistics`~~ | 已完成（2026-11-14），見下方說明 |
| 2 | ~~`datetime`、`pathlib`~~ | 已完成（2026-11-14），見下方說明 |
| 2 | `decimal` | 任意精度的十進位運算與 context，工作量最大，留到最後 |
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

### 第 2 優先的做法與限制（2026-11-14）

做法：用 rupy 寫成 `pylib/MODULE/__init__.py`，由 `src/pkgsrc.rs` 內建，兩個後端一起編譯，CPython 執行同一支測試時用真的模組對照。測試放在 `tests/corpus/py/stdlib/`（`tests/corpus/py/` 有 `numbers.py`，會擋住 CPython 的 `numbers` 模組）。

- `statistics`：CPython 用分數把資料加總得到精確值，最後只捨入一次。rupy 沒有大整數，改用浮點數展開式（Shewchuk，和 `math.fsum` 同一種），加總和平方和都是精確的；除法和開根號以「與中點比較」修正到正確捨入。所以 `mean`、`variance`、`pvariance`、`stdev`、`pstdev`、`harmonic_mean` 和 CPython 逐位元相同（另用 400 組隨機資料比對過）。
  - 資料是 `list[float]`。`mean`、`median`、`variance` 等在 CPython 收到 int 時，會依數值回傳 int 或 float，型別不固定，所以不收 int 串列。`fmean`、`stdev`、`pstdev`、`geometric_mean`、`median_grouped` 一律回傳 float，也收 int。
  - `mode`、`multimode`、`median_low`、`median_high` 收任何串列。
  - `NormalDist`：CPython 的 `inv_cdf` 是 C 寫的，clang 會把 `a * r + b` 合併成 FMA，rupy 用 `math.fma` 照做。`samples`、`kde` 沒做。
  - 已知差異：`harmonic_mean` 遇到 0 時 CPython 回傳 int 的 0，rupy 回傳 0.0；絕對值超過約 1e150 的資料，精確平方和會溢位，rupy 丟出 OverflowError。
- `fractions`：`Fraction` 的分子、分母是 64 位元整數，超過時丟出 OverflowError（和 rupy 的 int 相同）。`Fraction(n, d)` 只收 int，float 用 `Fraction.from_float(x)`；不和 float 混合運算。
  - 為此 rupy 新增「方法的聯集參數」：`def __add__(self, other: Fraction | int)` 依每個成員各編譯一份，不能用在 `__init__` 和類別階層。
- `csv`：照搬 CPython `_csv` 的狀態機與寫出規則。`reader`、`DictReader` 讀文字檔、`io.StringIO` 或字串串列；`writer`、`DictWriter` 寫到文字檔或 `io.StringIO`。
  - 限制：讀取用產生器實作，而 rupy 的產生器裡丟出的例外不能被呼叫端攔截，所以 `try: ... except csv.Error` 包住讀取的程式會在編譯時被拒絕。`QUOTE_NONNUMERIC` 讀取會產生 float，`DictReader` 欄位不足時 CPython 填 None，這兩種情況都直接報錯。
- `io.StringIO`：`@shared` 類別，`csv.writer(buf)` 保留 `buf` 之後，原變數仍看得到寫入的內容。
- `datetime`：照 CPython 的 `_pydatetime.py` 寫，錯誤訊息則以實際執行的 C 模組為準。只有 naive（沒有 tzinfo）的 `timedelta`、`date`、`time`、`datetime`。
  - `timedelta` 的參數是 float，小數部分照 C 的 `delta_new` 只捨入一次；int 在 2**53 以內換成 float 不會失真。
  - `strftime` 照 macOS C locale 的輸出；`strptime` 依 CPython 正規表示式中各選項的順序比對並回溯，所以「`unconverted data remains`」等錯誤訊息相同。
  - 限制：`datetime` 不是 `date` 的子類別（`isinstance(dt, date)` 為 False）；`date` 不能當 dict 的鍵；`now()`、`today()` 取當地時間（wasm 上由 JavaScript 提供）。
- `pathlib`：POSIX 的 `Path`。純路徑運算和 CPython 一樣；`parents`、`iterdir()`、`glob()` 回傳 list（CPython 是序列與產生器），`glob` 不支援 `**`，沒有 `parts`（長度不定的 tuple）。
  - 檔案操作（`mkdir`、`iterdir`、`glob` 等）在 wasm 上不能用：wasm 主機只有檔案，沒有目錄（`tests/corpus/py/stdlib/pathlib_files.py` 標成 wasm skip）。
- 配套的 rupy 變更：
  - 檔案改成共用的 handle（和 Python 一樣），所以 `csv.writer(f)` 可以保留 `f`。
  - `open(..., newline=...)`；讀檔預設把 `\r\n` 轉成 `\n`（之前沒轉）。
  - `TextIO` 型別註記、`math.nextafter`、`math.ulp`。
  - `math.hypot` 改成照搬 CPython 的 `vector_norm`：之前 Rust 用 libm、wasm 用 JavaScript 的版本，最後一位數可能不同。
- 順便修正的錯誤：
  - 超過 2**53 的 int / int 之前捨入兩次，現在只捨入一次。
  - 浮點數的 repr 之前可能和 CPython 差最後一位，例如 `1770740270910798.25` 印成 `.3`；現在取最短位數中最接近的值。
  - 套件裡 dataclass 的 repr 之前帶著 `PKG__` 前綴，現在拿掉了。
- 第二批（datetime、pathlib）的配套變更：
  - 方法的聯集回傳型別依位置對應聯集參數，例如 `__truediv__(self, other: timedelta | int) -> float | timedelta`。
  - `a + b` 在 `a.__add__` 不收 `b` 時改用 `b.__radd__`（`timedelta + date`）。
  - 套件改名時，類別裡的名字不再遮住方法裡的同名模組名稱（`datetime.date()` 方法與 `date` 類別）。
  - wasm：`time.strftime` 由 JavaScript 主機提供；只從不會執行到的程式碼呼叫的套件函數，不再讓整支程式變成「不支援」。

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
