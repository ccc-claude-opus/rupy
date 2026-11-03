# rupy

> rupy 原本是 py0，也就是 [ruai](https://github.com/ccc-llm/ruai) 的 `ruai py` 指令（更早之前是 py2rs 專案），現在是獨立的 crate。翻譯出的程式只依賴 `rupy` 中用到的執行期 feature。`numpy`／`sklearn` 套件在 rupy 裡；`gymnasium`、`torch` 與 `ruai.plot` 建在 ruai 的引擎上，只有用到它們時才會引入 ruai。`cargo install rupy` 也會安裝 `ruai-py` 與 `ruai-agent`，所以 `ruai py ...` 和 `ruai agent ...` 照樣能用。

[English](README.md) · 繁體中文 · [简体中文](README.cn.md)

把有型別標註的 Python 子集翻譯成可讀的 Rust。

```python
@dataclass
class Item:
    name: str
    price: float

def total(items: list[Item], tax: float = 0.05) -> float:
    return sum(i.price for i in items) * (1 + tax)
```

```rust
#[derive(Clone, Debug, PartialEq)]
pub struct Item {
    pub name: String,
    pub price: f64,
}

fn total(items: &[Item], tax: f64) -> f64 {
    pyrt::sum_f64(items.iter().map(|i| i.price)) * (1.0 + tax)
}
```

## 保證

1. **每個值都有靜態型別。** 函式要標註型別，區域變數由推導得出。
2. **看不出共享的差別。** Python 的名稱會共享可變物件，Rust 則是複製、移動或借用。
   只有在差別看不出來時 py2rs 才接受程式，並為每個參數推導出 `&T` / `&mut T` / `T`。
   （`@shared` 類別保留 Python 的共享語意，以 `Rc<RefCell<..>>` 實作。）
3. **輸出和 CPython 一樣，否則清楚報錯。** 無法保證的寫法會在翻譯時被拒絕，附上行號和
   提示，絕不會翻成行為不同的程式。
4. **可以直接使用 Rust crate**（`from rust.regex import Regex`）。

## 安裝與使用

```sh
cargo install rupy            # 或在原始碼目錄執行 cargo build --release
rupy emit  prog.py            # 印出 Rust 程式
rupy check prog.py            # 只檢查型別與所有權
rupy explain prog.py          # 參數模式、參考、複製、回傳 Result 的函式
rupy build prog.py [-o DIR]   # 產生 Cargo 專案並以 release 建置
rupy run   prog.py            # 建置（有快取）並執行
rupy pyo3  mod.py [-o DIR]    # Python 擴充模組（PyO3）：DIR/mod.so
rupy test                     # 與 CPython 的差分測試（在原始碼目錄）
rupy fuzz 300                 # 隨機程式與 CPython 比對
```

程式可以 import 自己的模組（`import geometry`、`from geometry import Point`，
`geometry.py` 放在同一個目錄）。

## 支援範圍

完整定義在 [SPEC.md](SPEC.md)（英文）。簡單說：`int`（64 位元，溢位會報錯）、
`float`、`bool`、`str`、`list`、`dict`、`set`、`tuple`、`Optional`；有預設值、關鍵字
參數與 `*args` 的函式；dataclass 與一般類別（方法、property、classmethod、運算子方法、
單一繼承）；例外（也可以有欄位）與 `try` / `finally`；推導式、f-string、`match`、
`with open`、generator、使用 `nonlocal` 的巢狀函式、lambda 與 `Callable`；泛型函式、
`Protocol` 與聯集型別參數（依引數型別分別編譯）；`math`、`collections`、`heapq`、
`bisect`、`itertools`、`functools`、`random`（同一個 seed 產生和 CPython 一樣的數字）、
`re`、`sys`、`time`、`json.dumps`、`os.path`。

一些寫法翻譯後的樣子（更多在 [docs/cases](docs/cases/README.md)）：

| Python | Rust |
|---|---|
| `x: T \| None`、`if x is not None:` | `Option<T>`、`if let Some(x) = &x` |
| `node.next = self.head; self.head = node` | `node.next = self.head.take();` |
| 只讀取的區域變數（`cur = cur.next`） | 參考：`let mut cur = &self.head;` |
| `item = self.items[k]; item.qty -= 1` | `let item = &mut self.items[k];` |
| 有子類別的類別 | 列舉已建立的類別的 `enum`，方法用 `match` 分派 |
| 呼叫者會接住的 `raise` | 只在那條路徑上回傳 `Result<T, PyErr>`，使用 `?` |
| 使用 `seen` 和 `nonlocal count` 的巢狀函式 | `fn dfs(.., seen: &mut HashSet<..>, count: &mut i64)`，每次呼叫時傳入 |
| `def first[T](xs: list[T]) -> T` | `first_int(xs: &[i64])`、`first_str(xs: &[String])`，每種引數型別一份 |
| `def gen(n) -> Iterator[int]: ... yield i` | `pyrt::Gen<i64>`：函式本體和使用端嚴格輪流執行 |
| `@shared class Node` | `struct Node(Rc<RefCell<NodeData>>)`，加上 getter 和 setter |

與 CPython 已知的差異：`int` 是 64 位元（超出範圍會引發 `OverflowError`）；set 的走訪
順序是插入順序（見 [TODO.md](TODO.md)）。

## 速度

`python3 bench/run.py`，CPython 3.14 與翻譯後的程式比較（Apple silicon）：

| 程式 | CPython | Rust | |
|---|---:|---:|---:|
| nbody（浮點數物件） | 1.21 s | 0.012 s | 101 倍 |
| matmul（浮點數串列） | 0.47 s | 0.013 s | 38 倍 |
| fib（遞迴） | 0.26 s | 0.013 s | 20 倍 |
| sieve | 0.48 s | 0.027 s | 18 倍 |
| graph（用 deque 的 BFS） | 0.14 s | 0.017 s | 8 倍 |
| objects（dataclass、排序、dict） | 0.59 s | 0.10 s | 6 倍 |
| printing | 0.21 s | 0.056 s | 4 倍 |
| strings、wordfreq | | | 2 倍 |

## 所有權標註

參數模式是推導出來的。要固定某個參數的模式就加上標註（`python/rust` 模組讓這些標註在
CPython 下也能執行；把該目錄加進 `PYTHONPATH`）：

```python
from rust import Ref, Mut, Own

def fill(xs: Mut[list[int]], n: int) -> None: ...   # &mut Vec<i64>
def keep(xs: Own[list[int]]) -> None: ...           # Vec<i64>
```

程式碼和標註矛盾時（例如修改 `Ref[...]`）會報錯。

## Rust crate

`from rust.CRATE import Name` 使用 Rust crate。宣告來自 stub 檔 `CRATE.pyi`，依序在
`./stubs`、`PY2RS_STUBS` 和 py2rs 附帶的 stub（`stubs/regex.pyi`）中尋找；該 crate
會成為產生出來的專案的 Cargo 相依套件。

```python
from rust.regex import Regex

date = Regex.new(r"(\d{4})-(\d{2})-(\d{2})")      # Result → 無效時引發 ValueError
print(date.replace_all("on 2024-05-17", "$3/$2/$1"))
```

stub 是有型別宣告的 Python 檔，每個宣告對應一個 Rust 路徑或運算式範本
（`@rust("{self}.find({0}).map(|m| m.as_str().to_string())")`）。`rupy stub
CRATE[@VERSION]` 會從 crate 的 rustdoc JSON 產生 stub。`from rust import inline` 是
逃生口：`inline("xs.sort_unstable();")`、`inline[int]("n.count_ones() as i64")`。

## Python 擴充模組

`rupy pyo3 mod.py` 建置出 `mod.so`，Python 可以像原本的模組一樣 import。模組層級的
函式會被匯出（引數與回傳值可以是 int、float、bool、str、list、tuple、dict 和
`None`）；函式引發的例外會在 Python 中以相同類別引發；`print` 寫到 Python 的
`sys.stdout`。`tests/pyo3/run.sh` 檢查 import 這個模組印出的內容和 import 原本的
Python 檔相同。

## 範例：套件與 `ruai agent`

### LLM agent 團隊（`ruai agent`）

```bash
ruai agent init                                   # 在目前目錄建立 .agge/（設定、agent、graph、紀錄）
ruai agent model add glm nvidia z-ai/glm-5.3-flash   # provider：openai、nvidia、openrouter、deepseek、groq、gemini、ollama、lmstudio、anthropic
ruai agent chat --team code                       # 與 lead 對話，lead 以 <delegate> 分派給 architect / coder / tester / reviewer
ruai agent ask -y "建立 hello.py 並執行"            # 單次任務：agent 以文字標籤呼叫工具（讀寫檔、搜尋、shell）
ruai agent book "Git 入門" --chapters 3 -o gitBook   # 大綱 → 各章（map 節點）→ 總編輯
ruai agent run brainstorm "如何設計快取層" -M merge=claude
```

`ruai agent` 是 [agge](src/agent/README.md)（約 2,500 行的 Python）以 rupy 改寫後翻成 Rust、編進 `ruai-agent` 執行檔（`cargo install rupy`；ruai 遇到 `ruai agent` 會執行 `ruai-agent`），不需要 Python 或 cargo。同一份原始碼（`src/agent/*.py`）也能直接以 CPython 執行；`tests/agent.rs` 用同一串指令（含一個假的 OpenAI / Anthropic 串流伺服器）比對兩者的輸出逐字相同，並檢查嵌入的翻譯 `src/agent/agent_gen.rs` 是最新的。與原版的差異：平行的 delegate、graph 節點與 map 項目改為依序執行；聊天介面沒有 readline 歷史與補完。

### rupy 的 numpy

```python
import numpy as np

rng = np.random.default_rng(0)
x = rng.random((50, 3))
y = x @ np.array([2.0, -1.0, 0.5]) + 0.3
w = np.zeros(3)
for _ in range(2000):
    err = x @ w - y
    w = w - 0.5 * (x.T @ err) / x.shape[0]
print(np.round(w, 3), x[x[:, 0] > 0.9].shape, round(float(np.abs(x @ w - y).mean()), 6))
```

`import numpy as np` 在 rupy 中是以 Rust 實作的 NumPy 子集（`src/pyrt/lib/numpy/`）：float64 / int64 / bool 陣列、NumPy 2 的型別提升與廣播、切片是共用記憶體的 view、布林遮罩與索引陣列、沿軸的歸約（`sum` 採用 NumPy 的 pairwise 加總順序）、`linalg`、與 NumPy 逐位元相同的 `random.default_rng`；`print` / `repr` 與 NumPy 的 `arrayprint` 逐字相同。同一支程式用 CPython 執行時就是真的 NumPy，`tests/corpus/numpy/` 逐支比對。因為 rupy 是靜態型別：`a[i]` 與歸約的結果是 0 維陣列（NumPy scalar），需要 Python float 時寫 `float(a.sum())`；`a.shape` 可索引但不能拆包；dtype 用字串（`dtype="int64"`）。浮點矩陣乘法依序加總，可能與 NumPy 的 BLAS 在最後一位不同。

### rupy 的 sklearn

```python
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

iris = load_iris()
Xtr, Xte, ytr, yte = train_test_split(iris.data, iris.target, test_size=0.3, random_state=42)
sc = StandardScaler().fit(Xtr)
model = LogisticRegression().fit(sc.transform(Xtr), ytr)
print(model, model.score(sc.transform(Xte), yte))
```

`from sklearn.X import Y` 在 rupy 中是以 Rust 實作、建在 numpy 陣列上的 scikit-learn 子集（`src/pyrt/lib/sklearn/`）：`LinearRegression`、`Ridge`、`LogisticRegression`、`KNeighborsClassifier` / `Regressor`、`GaussianNB`、`KMeans`、`PCA`、`StandardScaler`、`MinMaxScaler`、`train_test_split`、常用指標與 `load_iris`。演算法依照 scikit-learn（相同的置中、求解器的最佳解、PCA 的正負號慣例、`train_test_split` 用同樣的 `RandomState` 亂數，所以切分完全相同），`tests/corpus/sklearn/` 以真的 scikit-learn 對照輸出。差異：scikit-learn 提早停止的迭代求解器（lbfgs）只在其容許誤差內相同；k-NN 距離剛好相等時可能選到不同的鄰居；`KMeans` 需要給初始中心（`init=陣列`）；`target_names` 是 list。

### rupy 的 gymnasium 與 torch

```python
import gymnasium as gym
import torch
import torch.nn as nn

torch.manual_seed(0)
policy = nn.Sequential(nn.Linear(4, 32), nn.Tanh(), nn.Linear(32, 2))
env = gym.make("CartPole-v1")
obs, info = env.reset(seed=42)
logits = policy(torch.from_numpy(obs))
obs, reward, terminated, truncated, info = env.step(int(logits.argmax()))
print(policy, logits, obs, reward)
```

`import gymnasium as gym` 是 `ruai::world` 的環境套上 Gymnasium 的 Python API（觀測值是 float32 的 numpy 陣列，與 Gymnasium 逐位元相同）；`import torch` 是建在 ruai nn 引擎上的 PyTorch 子集：autograd、`nn.Linear` 等模組、`nn.Sequential`、損失函數、`optim.SGD` / `Adam`、`torch.no_grad()`。`torch.manual_seed` 重現 PyTorch 的亂數產生器（MT19937），所以 `rand`、`randn` 與 `nn.Linear` 的初始權重都與 PyTorch 相同；張量與模組的印出格式也一樣。`tests/corpus/gymnasium/`、`tests/corpus/torch/` 以真的 Gymnasium 與 PyTorch 對照（訓練迴圈在 PyTorch 預設的 4 位小數下相同）。差異：模型用 `nn.Sequential` 或持有各層的一般類別（不能繼承 `nn.Module`），`parameters()` 回傳 list；dtype 在 rupy 中是字串；矩陣乘積與元素函數可能與 PyTorch 的 BLAS / 向量化實作在最後一位不同。

## 測試

`rupy test [檔案|目錄]`（預設 `tests/`）翻譯每個程式，全部放進一個 Cargo 套件建置，
再和 CPython（`PY2RS_PYTHON`，否則 python3.14 / 3.13 / 3.12）比較標準輸出、結束碼和
例外型別。有 `NAME.in` 時當作輸入。第一行是 `# error: TEXT` 的程式必須被拒絕，而且
錯誤訊息要包含 TEXT（`tests/err/`）。測試集約有 240 個程式和 45 個拒絕案例；
`rupy fuzz` 另外產生隨機程式。

## 原始碼結構

- `src/front.rs`（及 `src/front/`）：ruff 剖析的 AST → 有型別的 IR（`src/ir.rs`）；
  標準函式庫、`re`、運算子方法、巢狀函式、`match`、泛型
- `src/own.rs`：所有權推導、活性分析、共享與走訪檢查、參考
- `src/exc.rs`：哪些例外會在哪裡被接住，因而決定哪些函式回傳 `Result`
- `src/gen.rs`（及 `src/gen/`）：IR → Rust
- `src/modules.rs`：多檔案程式；`src/pyo3.rs`：擴充模組
- `pyrt/`：執行期函式庫：Python 的輸出格式、格式規格、`//` `%` `**` 語意、以字元為
  單位的 `str` 方法、例外、標準函式庫、generator、緩衝輸出
