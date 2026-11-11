# rupy

> rupy 原本是 py0，也就是 [ruai](https://github.com/ccc-llm/ruai) 的 `ruai py` 命令（更早之前是 py2rs 项目），现在是独立的 crate。翻译出的程序只依赖 `rupy` 中用到的运行时 feature。`numpy`／`sklearn` 包在 rupy 里；`gymnasium`、`torch` 与 `ruai.plot` 建在 ruai 的引擎上，只有用到它们时才会引入 ruai。`cargo install rupy` 也会安装 `ruai-py` 与 `ruai-agent`，所以 `ruai py ...` 和 `ruai agent ...` 照样能用。

[English](README.md) · [繁體中文](README.tw.md) · 简体中文

把有类型注解的 Python 子集翻译成可读的 Rust。

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

## 保证

1. **每个值都有静态类型。** 函数要注解类型，局部变量由推导得出。
2. **看不出共享的差别。** Python 的名称会共享可变对象，Rust 则是拷贝、移动或借用。
   只有在差别看不出来时 py2rs 才接受程序，并为每个参数推导出 `&T` / `&mut T` / `T`。
   （`@shared` 类保留 Python 的共享语义，以 `Rc<RefCell<..>>` 实现。）
3. **输出和 CPython 一样，否则清楚报错。** 无法保证的写法会在翻译时被拒绝，附上行号和
   提示，绝不会翻成行为不同的程序。
4. **可以直接使用 Rust crate**（`from rust.regex import Regex`）。

## 安装与使用

```sh
cargo install rupy            # 或在原代码目录运行 cargo build --release
rupy emit  prog.py            # 印出 Rust 程序
rupy check prog.py            # 只检查类型与所有权
rupy explain prog.py          # 参数模式、引用、拷贝、返回 Result 的函数
rupy build prog.py [-o DIR]   # 产生 Cargo 项目并以 release 构建
rupy run   prog.py            # 构建（有缓存）并运行
rupy pyo3  mod.py [-o DIR]    # Python 扩展模块（PyO3）：DIR/mod.so
rupy test                     # 与 CPython 的差分测试（在原代码目录）
rupy fuzz 300                 # 随机程序与 CPython 比对
```

程序可以 import 自己的模块（`import geometry`、`from geometry import Point`，
`geometry.py` 放在同一个目录）。

## 支持范围

完整定义在 [SPEC.md](SPEC.md)（英文）。简单说：`int`（64 位，溢出会报错）、
`float`、`bool`、`str`、`list`、`dict`、`set`、`tuple`、`Optional`；有默认值、关键字
参数与 `*args` 的函数；dataclass 与一般类（方法、property、classmethod、操作符方法、
单一继承）；异常（也可以有字段）与 `try` / `finally`；推导式、f-string、`match`、
`with open`、generator、使用 `nonlocal` 的嵌套函数、lambda 与 `Callable`；泛型函数、
`Protocol` 与联合类型参数（依参数类型分别编译）；`math`、`collections`、`heapq`、
`bisect`、`itertools`、`functools`、`random`（同一个 seed 产生和 CPython 一样的数字）、
`re`、`sys`、`time`、`json.dumps`、`os.path`。

一些写法翻译后的样子（更多在 [docs/cases](docs/cases/README.md)）：

| Python | Rust |
|---|---|
| `x: T \| None`、`if x is not None:` | `Option<T>`、`if let Some(x) = &x` |
| `node.next = self.head; self.head = node` | `node.next = self.head.take();` |
| 只读取的局部变量（`cur = cur.next`） | 引用：`let mut cur = &self.head;` |
| `item = self.items[k]; item.qty -= 1` | `let item = &mut self.items[k];` |
| 有子类的类 | 枚举已创建的类的 `enum`，方法用 `match` 分派 |
| 调用者会接住的 `raise` | 只在那条路径上返回 `Result<T, PyErr>`，使用 `?` |
| 使用 `seen` 和 `nonlocal count` 的嵌套函数 | `fn dfs(.., seen: &mut HashSet<..>, count: &mut i64)`，每次调用时传入 |
| `def first[T](xs: list[T]) -> T` | `first_int(xs: &[i64])`、`first_str(xs: &[String])`，每种参数类型一份 |
| `def gen(n) -> Iterator[int]: ... yield i` | `pyrt::Gen<i64>`：函数本体和使用端严格轮流运行 |
| `@shared class Node` | `struct Node(Rc<RefCell<NodeData>>)`，加上 getter 和 setter |

与 CPython 已知的差异：`int` 是 64 位（超出范围会引发 `OverflowError`）；set 的遍历
顺序是插入顺序（见 [TODO.md](TODO.md)）。

## 速度

`python3 bench/run.py`，CPython 3.14 与翻译后的程序比较（Apple silicon）：

| 程序 | CPython | Rust | |
|---|---:|---:|---:|
| nbody（浮点数对象） | 1.21 s | 0.012 s | 101 倍 |
| matmul（浮点数列表） | 0.47 s | 0.013 s | 38 倍 |
| fib（递归） | 0.26 s | 0.013 s | 20 倍 |
| sieve | 0.48 s | 0.027 s | 18 倍 |
| graph（用 deque 的 BFS） | 0.14 s | 0.017 s | 8 倍 |
| objects（dataclass、排序、dict） | 0.59 s | 0.10 s | 6 倍 |
| printing | 0.21 s | 0.056 s | 4 倍 |
| strings、wordfreq | | | 2 倍 |

## 所有权注解

参数模式是推导出来的。要固定某个参数的模式就加上注解（`python/rust` 模块让这些注解在
CPython 下也能运行；把该目录加进 `PYTHONPATH`）：

```python
from rust import Ref, Mut, Own

def fill(xs: Mut[list[int]], n: int) -> None: ...   # &mut Vec<i64>
def keep(xs: Own[list[int]]) -> None: ...           # Vec<i64>
```

代码和注解矛盾时（例如修改 `Ref[...]`）会报错。

## WebAssembly

`rupy wasm FILE.py [-o OUT.wasm]` 不经过 Rust，直接把程序编译成 WebAssembly：一个 WasmGC 模块（对象、list、dict、set、tuple、字符串用 GC 的 struct 与 array；Python 的异常用 wasm 异常），加上运行它的 JavaScript 主机 `rupy_wasm.mjs`，可以在浏览器（`run(bytes, {stdout, stderr, stdin})`）或 Node.js 22 以上（`node rupy_wasm.mjs OUT.wasm`）运行。`rupy wasm --run FILE.py` 编译后直接运行，`rupy test --wasm` 把能编译的程序和 CPython 对照。

编译器本身也能编成 `wasm32-unknown-unknown`（`examples/rupy_wasm.rs`），所以 `web/` 的 playground 与 [rupy IDE](ide/README.md) 都在浏览器里编译 rupy。用 Rust 实现的包（numpy、sklearn 等）放在另一个模块 `rupy_lib.wasm`，程序需要时才加载。

文本文件可以用：`open()` 读写主机的 `io.files`（任何有 `get(path)` 与 `set(path, text)` 的对象，例如 `Map`；Node.js 下直接读写磁盘），所以网页可以把文件交给程序，再拿回它写出的文件。rupy IDE 就是这样：`open("data.csv")` 读工作区的文件，rstatistics 的 `g.save("hist.svg")` 把图存进工作区。

`random` 的随机数和 CPython 相同（Mersenne Twister 在主机里），`itertools` 按 CPython 的顺序生成 list，`re` 在 `rupy_lib.wasm` 里用和原生后端相同的 regex crate 匹配，结果和原生后端一样。

wasm 后端还不支持：generator、把函数当值传递（lambda 当 `key=` 参数可以）、`nonlocal`、`heapq`、异常的自定义字段，以及 `ruai.plot`。`log`、`exp` 等超越函数用 JavaScript 的 `Math`，结果的最后一位可能和 CPython 不同。

## Rust crate

`from rust.CRATE import Name` 使用 Rust crate。声明来自 stub 档 `CRATE.pyi`，依序在
`./stubs`、`PY2RS_STUBS` 和 py2rs 附带的 stub（`stubs/regex.pyi`）中寻找；该 crate
会成为产生出来的项目的 Cargo 依赖。

```python
from rust.regex import Regex

date = Regex.new(r"(\d{4})-(\d{2})-(\d{2})")      # Result → 无效时引发 ValueError
print(date.replace_all("on 2024-05-17", "$3/$2/$1"))
```

stub 是有类型声明的 Python 档，每个声明对应一个 Rust 路径或表达式范本
（`@rust("{self}.find({0}).map(|m| m.as_str().to_string())")`）。`rupy stub
CRATE[@VERSION]` 会从 crate 的 rustdoc JSON 产生 stub。`from rust import inline` 是
后门：`inline("xs.sort_unstable();")`、`inline[int]("n.count_ones() as i64")`。

## Python 扩展模块

`rupy pyo3 mod.py` 构建出 `mod.so`，Python 可以像原本的模块一样 import。模块层级的
函数会被导出（参数与返回值可以是 int、float、bool、str、list、tuple、dict 和
`None`）；函数引发的异常会在 Python 中以相同类引发；`print` 写到 Python 的
`sys.stdout`。`tests/pyo3/run.sh` 检查 import 这个模块印出的内容和 import 原本的
Python 档相同。

## 示例：包与 `ruai agent`

### LLM agent 团队（`ruai agent`）

```bash
ruai agent init                                   # 在当前目录建立 .agge/（设置、agent、graph、记录）
ruai agent model add glm nvidia z-ai/glm-5.3-flash   # provider：openai、nvidia、openrouter、deepseek、groq、gemini、ollama、lmstudio、anthropic
ruai agent chat --team code                       # 与 lead 对话，lead 以 <delegate> 分派给 architect / coder / tester / reviewer
ruai agent ask -y "建立 hello.py 并运行"            # 单次任务：agent 以文字标签调用工具（读写文件、搜索、shell）
ruai agent book "Git 入门" --chapters 3 -o gitBook   # 大纲 → 各章（map 节点）→ 总编辑
ruai agent run brainstorm "如何设计缓存层" -M merge=claude
```

`ruai agent` 是 [agge](src/agent/README.md)（约 2,500 行的 Python）以 rupy 改写后翻译成 Rust、编进 `ruai-agent` 可执行文件（`cargo install rupy`；ruai 遇到 `ruai agent` 会运行 `ruai-agent`），不需要 Python 或 cargo。同一份源代码（`src/agent/*.py`）也能直接以 CPython 运行；`tests/agent.rs` 用同一串命令（含一个假的 OpenAI / Anthropic 流服务器）对比两者的输出逐字相同，并检查嵌入的翻译 `src/agent/agent_gen.rs` 是最新的。与原版的差异：并行的 delegate、graph 节点与 map 项改为依次执行；聊天界面没有 readline 历史与补全。

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

`import numpy as np` 在 rupy 中是以 Rust 实现的 NumPy 子集（`src/pyrt/lib/numpy/`）：float64 / int64 / bool 数组、NumPy 2 的类型提升与广播、切片是共享内存的 view、布尔掩码与索引数组、沿轴的归约（`sum` 采用 NumPy 的 pairwise 求和顺序）、`linalg`、与 NumPy 逐位相同的 `random.default_rng`；`print` / `repr` 与 NumPy 的 `arrayprint` 逐字相同。同一个程序用 CPython 运行时就是真正的 NumPy，`tests/corpus/numpy/` 逐个对比。因为 rupy 是静态类型：`a[i]` 与归约的结果是 0 维数组（NumPy scalar），需要 Python float 时写 `float(a.sum())`；`a.shape` 可索引但不能解包；dtype 用字符串（`dtype="int64"`）。浮点矩阵乘法依次求和，可能与 NumPy 的 BLAS 在最后一位不同。

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

`from sklearn.X import Y` 在 rupy 中是以 Rust 实现、建立在 numpy 数组上的 scikit-learn 子集（`src/pyrt/lib/sklearn/`）：`LinearRegression`、`Ridge`、`LogisticRegression`、`KNeighborsClassifier` / `Regressor`、`GaussianNB`、`KMeans`、`PCA`、`StandardScaler`、`MinMaxScaler`、`train_test_split`、常用指标与 `load_iris`。算法遵循 scikit-learn（相同的中心化、求解器的最佳解、PCA 的正负号惯例、`train_test_split` 用同样的 `RandomState` 随机数，所以切分完全相同），`tests/corpus/sklearn/` 用真正的 scikit-learn 对照输出。差异：scikit-learn 提前停止的迭代求解器（lbfgs）只在其允许误差内相同；k-NN 距离刚好相等时可能选到不同的邻居；`KMeans` 需要给初始中心（`init=数组`）；`target_names` 是 list。

### rupy 的 gymnasium 与 torch

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

`import gymnasium as gym` 是 `ruai::world` 的环境套上 Gymnasium 的 Python API（观测值是 float32 的 numpy 数组，与 Gymnasium 逐位相同）；`import torch` 是建立在 ruai nn 引擎上的 PyTorch 子集：autograd、`nn.Linear` 等模块、`nn.Sequential`、损失函数、`optim.SGD` / `Adam`、`torch.no_grad()`。`torch.manual_seed` 复现 PyTorch 的随机数生成器（MT19937），所以 `rand`、`randn` 与 `nn.Linear` 的初始权重都与 PyTorch 相同；张量与模块的打印格式也一样。`tests/corpus/gymnasium/`、`tests/corpus/torch/` 用真正的 Gymnasium 与 PyTorch 对照（训练循环在 PyTorch 默认的 4 位小数下相同）。差异：模型用 `nn.Sequential` 或持有各层的一般类（不能继承 `nn.Module`），`parameters()` 返回 list；dtype 在 rupy 中是字符串；矩阵乘积与逐元素函数可能与 PyTorch 的 BLAS / 向量化实现在最后一位不同。

### rupy 的 rstatistics（R 的概率统计）

```python
import rstatistics as r

x = [5.1, 4.9, 6.2, 5.8, 6.0, 5.5, 5.3, 6.1]
print(r.t_test(x, mu=5.0))
print(r.summary(x))
print(r.qt(0.975, 7))
g = r.set_seed(42)
print(r.print_vector(g.rnorm(5)))
```

`import rstatistics as r` 是 R 的概率统计函数：17 种分布的 `d` / `p` / `q`、`set_seed` 之后与 R 相同的随机数（Mersenne-Twister、反函数法的正态随机数、`sample`；所有分布的随机数都与 R 的 `src/nmath` 一位不差）、`t_test`、`var_test`、`chisq_test`、`binom_test`、`prop_test`、`cor_test`、非参数检验（`wilcox_test`、`ks_test`、`shapiro_test`、`fisher_test`、`kruskal_test`）、`p_adjust`、`table`、线性模型（`lm`、`anova`、`aov`、`predict`）、`summary`、`quantile`（九种）等，打印格式与 R 一字不差；还有 R 绘图的样子（`graphics()` 打开一个写入 SVG 的设备，布局与 R 相同：`hist`、`density`、`boxplot`、`qqnorm`、`ecdf`、`curve`、`barplot`、`plot`）。名称沿用 R，`.` 改成 `_`（`t.test` → `t_test`、`lower.tail` → `lower_tail`）。rstatistics 是用 rupy 本身写成的包（`rstatistics/`，在 PyPI 上是纯 Python、无依赖，需要 Python 3.13 以上），rupy 把它的源代码和程序一起编译，所以 Rust 与 wasm 后端都能用。`rstatistics/tests/run.py` 与 R 4.6 对照：打印结果相同，分布函数的相对误差在 1e-12 内。

## 测试

`rupy test [文件|目录]`（缺省 `tests/`）翻译每个程序，全部放进一个 Cargo 包构建，
再和 CPython（`PY2RS_PYTHON`，否则 python3.14 / 3.13 / 3.12）比较标准输出、结束码和
异常类型。有 `NAME.in` 时当作输入。第一行是 `# error: TEXT` 的程序必须被拒绝，而且
错误消息要包含 TEXT（`tests/err/`）。测试集约有 240 个程序和 45 个拒绝案例；
`rupy fuzz` 另外产生随机程序。

## 原代码结构

- `src/front.rs`（及 `src/front/`）：ruff 解析的 AST → 有类型的 IR（`src/ir.rs`）；
  标准库、`re`、操作符方法、嵌套函数、`match`、泛型
- `src/own.rs`：所有权推导、活跃性分析、共享与遍历检查、引用
- `src/exc.rs`：哪些异常会在哪里被接住，因而决定哪些函数返回 `Result`
- `src/gen.rs`（及 `src/gen/`）：IR → Rust
- `src/modules.rs`：多文件程序；`src/pyo3.rs`：扩展模块
- `pyrt/`：运行时库：Python 的输出格式、格式规格、`//` `%` `**` 语义、以字符为
  单位的 `str` 方法、异常、标准库、generator、缓冲输出
