# rupy 的簡易版 sympy 規劃

狀態：延後（2026-11-06）。依 [stdlib-plan.md](stdlib-plan.md) 的方針，外部套件暫時用 Python 橋接，不做原生實作。若日後要做，採用做法 A：Rust 實作，模式同 numpy。

目標：rupy 程式 `import sympy` 後，在 Rust、wasm、瀏覽器上都能執行，輸出和真的 sympy 一字不差。CPython 下直接執行真的 sympy，作為對照組。

## 架構（同 numpy）

- Rust 實作放在 `src/pyrt/lib/sympy/`，stub 放在 `src/lib/sympy.pyi`；cargo feature 名為 `sympy`。
- 表達式用 Rust `enum` 表示（`Symbol`、`Integer`、`Rational`、`Float`、`Add`、`Mul`、`Pow`、`Function`、常數），共享子樹用 `Rc`。
- 大整數用 `num-bigint` / `num-rational`，有理數運算不會溢位。
- 運算子多載寫在 stub：`Expr` 與 `int` / `float` 雙向都能運算（`x + 1`、`2 * x`、`1 / x`、`x ** 2`）。
- wasm 經由現有的 rupy_lib 橋接，物件以 handle 傳遞。
- 測試放在 `tests/corpus/sympy/`，每支程式都和 CPython 的真 sympy 比對輸出，wasm 也要一致。

## 範圍

第一批：
- 物件：`Symbol`、`symbols("x y")`（回傳 `list[Symbol]`，用 `x, y = symbols("x y")` 拆開）、`Integer`、`Rational`、`Float`、`pi`、`E`、`I`、`oo`。
- 函數：`sin`、`cos`、`tan`、`exp`、`log`、`sqrt`、`Abs`。
- 建構時的自動化簡，規則和 sympy 相同：合併同類項、整理係數、`sqrt(8) → 2*sqrt(2)`、`sin(pi) → 0`。
- 操作：`expand`、`diff`、`subs`、`evalf` / `N`、`str` / `repr`。

第二批：
- `factor`：單變數整係數多項式。
- `solve`：一次、二次、有理根的多項式方程，以及線性方程組。
- `integrate`：多項式、`exp(a*x)`、`sin` / `cos` 的線性參數、查表積分。
- `limit`：簡單情形。
- `Matrix`：小矩陣的 `det`、`inv`、`solve`。
- `latex()`。

不做或延後：
- 完整的 `simplify`：sympy 的 `simplify` 是啟發式組合，難以逐字一致，只做確定的規則。
- 其他：`series`、`dsolve`、`pprint`。
- `lambdify`：需要函數當值，wasm 後端不支援。

## 難點

1. 輸出順序：要照搬 sympy 的 `sort_key` 與 `StrPrinter` 規則，例如 `x**2 + 2*x + 1`、`-x + y`、`2*x*y`。這是工作量最大、最需要逐案比對的部分。
2. 自動化簡：`Add`、`Mul`、`Pow` 在建構時的規則必須完全一致，`expand`、`diff` 的結果才會相同。
3. `evalf`：sympy 用 mpmath，預設 15 位有效數字，印法和 Python 的 `float` 不同（例如 `1.41421356237310`）。至少要正確做到 15 位精度。
4. 型別：`solve` 依輸入不同，可能回傳 list 或 list of dict，要拆成固定型別的形式或多載。

## 階段

| 階段 | 內容 | 完成條件 |
| --- | --- | --- |
| 1 | 表達式樹、大整數有理數、自動化簡、`str` 輸出 | 建構與印出和 sympy 逐字相同 |
| 2 | `expand`、`diff`、`subs`、`evalf` | 語料對照通過 |
| 3 | `factor`、`solve`、`integrate` | 語料對照通過 |
| 4 | `Matrix`、`latex`、wasm 與瀏覽器、README / CHANGELOG | wasm 語料也全部一致 |

每完成一個階段就 commit 一次。預估 Rust 核心約 3,000–5,000 行。
