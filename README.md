# rupy

> rupy was py0, the `ruai py` command of [ruai](https://github.com/ccc-llm/ruai) (and before that the project py2rs); it is now its own crate. Translated programs depend on `rupy` with only the runtime features they need. The `numpy` / `sklearn` packages are in rupy; `gymnasium`, `torch` and `ruai.plot` run on ruai's engine, which rupy pulls in only for them. `cargo install rupy` also installs `ruai-py` and `ruai-agent`, so `ruai py ...` and `ruai agent ...` keep working.

English · [繁體中文](README.tw.md) · [简体中文](README.cn.md)

A translator from a typed subset of Python to readable Rust.

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

## Promises

1. **Every value has a static type.** Functions are annotated; locals are inferred.
2. **No observable sharing.** Python shares mutable objects between names; Rust copies,
   moves or borrows them. py2rs accepts a program only when the difference cannot be
   seen, and infers `&T` / `&mut T` / `T` for every parameter. (`@shared` classes keep
   Python's sharing, as `Rc<RefCell<..>>`.)
3. **Same output as CPython, or a clear error.** Anything that cannot be guaranteed is
   rejected at translation time with the line and a hint, never translated differently.
4. **Rust crates can be used directly** (`from rust.regex import Regex`).

## Install and use

```sh
cargo install rupy             # or: cargo build --release in a checkout
rupy emit  prog.py            # print the Rust program
rupy check prog.py            # types + ownership only
rupy explain prog.py          # parameter modes, references, copies, Result functions
rupy build prog.py [-o DIR]   # Cargo project, release build
rupy run   prog.py            # build (cached) and run
rupy pyo3  mod.py [-o DIR]    # a Python extension module (PyO3): DIR/mod.so
rupy test                     # differential test against CPython (a checkout)
rupy fuzz 300                 # random programs against CPython
```

A program may import its own modules (`import geometry`, `from geometry import Point`
with `geometry.py` next to it).

## What is supported

The full definition is [SPEC.md](SPEC.md). In short: `int` (64-bit, overflow is an
error), `float`, `bool`, `str`, `list`, `dict`, `set`, `tuple`, `Optional`; functions
with defaults, keywords and `*args`; dataclasses and classes with methods, properties,
class methods, operator methods and single inheritance; exceptions (also with fields)
and `try` / `finally`; comprehensions, f-strings, `match`, `with open`, generators,
nested functions with `nonlocal`, lambdas and `Callable`; generic functions, `Protocol`
and union parameters (compiled per argument type); `math`, `collections`, `heapq`,
`bisect`, `itertools`, `functools`, `random` (same numbers as CPython for the same
seed), `re`, `sys`, `time`, `json.dumps`, `os.path`.

How some constructs come out (more in [docs/cases](docs/cases/README.md)):

| Python | Rust |
|---|---|
| `x: T \| None`, `if x is not None:` | `Option<T>`, `if let Some(x) = &x` |
| `node.next = self.head; self.head = node` | `node.next = self.head.take();` |
| a local that only reads (`cur = cur.next`) | a reference: `let mut cur = &self.head;` |
| `item = self.items[k]; item.qty -= 1` | `let item = &mut self.items[k];` |
| a class with subclasses | an `enum` over the created classes, methods dispatch with `match` |
| a `raise` that a caller catches | `Result<T, PyErr>` on that path only, `?` |
| a nested function using `seen` and `nonlocal count` | `fn dfs(.., seen: &mut HashSet<..>, count: &mut i64)`, the variables passed at each call |
| `def first[T](xs: list[T]) -> T` | `first_int(xs: &[i64])`, `first_str(xs: &[String])`, one per argument type |
| `def gen(n) -> Iterator[int]: ... yield i` | `pyrt::Gen<i64>`: the body runs strictly in turn with its consumer |
| `@shared class Node` | `struct Node(Rc<RefCell<NodeData>>)` with getters and setters |

Known differences from CPython: `int` is 64-bit (results beyond it raise
`OverflowError`); set iteration order is insertion order ([TODO.md](TODO.md)).

## Speed

`python3 bench/run.py`, CPython 3.14 against the translated program (Apple silicon):

| program | CPython | Rust | |
|---|---:|---:|---:|
| nbody (float objects) | 1.21 s | 0.012 s | 101x |
| matmul (lists of floats) | 0.47 s | 0.013 s | 38x |
| fib (recursion) | 0.26 s | 0.013 s | 20x |
| sieve | 0.48 s | 0.027 s | 18x |
| graph (BFS with deque) | 0.14 s | 0.017 s | 8x |
| objects (dataclasses, sort, dict) | 0.59 s | 0.10 s | 6x |
| printing | 0.21 s | 0.056 s | 4x |
| strings, wordfreq | | | 2x |

## Ownership annotations

Parameter modes are inferred. To pin one, annotate it (the module `python/rust` makes the
annotations work under CPython too; put that directory on `PYTHONPATH`):

```python
from rust import Ref, Mut, Own

def fill(xs: Mut[list[int]], n: int) -> None: ...   # &mut Vec<i64>
def keep(xs: Own[list[int]]) -> None: ...           # Vec<i64>
```

An annotation the code contradicts (modifying a `Ref[...]`) is an error.

## Packages and the standard library

`import M`, `import M as A` and `from M import x` also find **rupy packages**: stubs `M.pyi`
in `src/lib/` (or in a directory listed in `RUPY_LIB`), whose declarations map to Rust
under `rupy::pyrt::lib::M`. A stub declares classes, functions and constants in typed Python;
a parameter typed `A | B` makes overloads (a generic Rust function), several `def`s of one
name are overloads, `@rust("...")` gives a Rust path or an expression template, and
`Result[T, OSError | ...]` raises CPython's exceptions.

- **The standard library**, module by module, each checked against CPython
  (`tests/corpus/py/std_*.py`): `shlex`, `fnmatch`, `html`, `subprocess`, more of `os` /
  `os.path` / `sys` / `time`, besides the modules built into the translator (`math`,
  `collections`, `heapq`, `bisect`, `itertools`, `functools`, `random`, `re`, `sys`, `time`,
  `json.dumps`, `os.path`).
- **numpy**: float64 / float32 / int64 / bool arrays with NumPy 2's promotion,
  broadcasting, views, masks and index arrays, reductions in NumPy's summation order,
  `linalg`, `random.default_rng`; printing identical to NumPy's.
- **sklearn**: linear and logistic regression, ridge, k-NN, Gaussian naive Bayes, KMeans,
  PCA, scalers, `train_test_split` (the same split as scikit-learn), metrics, `load_iris`.
- **gymnasium**: ruai's environments with Gymnasium's API, bit for bit.
- **torch**: tensors with autograd on ruai's nn engine, `nn` modules, losses, `optim`,
  `torch.no_grad()`, and PyTorch's random numbers for `torch.manual_seed`.
- **ruai.plot**: matplotlib.pyplot's API in Rust; `show()` draws on a canvas in the
  browser, `savefig` writes SVG or HTML; limits and ticks as matplotlib's.
- **rupy.json**, **rupy.http**: a typed JSON value and an HTTP(S) client, with CPython
  stand-ins in `python/rupy/`.
- **rstat**: R's probability and statistics functions (`d`/`p`/`q` of 17 distributions,
  `set_seed` with R's random numbers, `t_test` and the other common tests, `summary`,
  `quantile`, ...), printed as R prints them. Unlike the packages above it is written in
  rupy itself (`rstat/`, also on PyPI as pure Python: `pip install rupy-rstat`): rupy compiles its source with the
  program, so it runs on the Rust and the wasm backends alike. See
  [rstat/README.md](rstat/README.md).

Under CPython the same programs import the real modules (matplotlib for `ruai.plot`);
`tests/corpus/numpy`, `sklearn`, `gymnasium`, `torch`, `plot` and `rstat` compare the two
(`rstat/tests/run.py` compares rstat with R itself).

```python
import shlex
from fnmatch import fnmatch

import numpy as np

words: list[str] = shlex.split("cp 'my file.txt' backup/")
print(words, fnmatch("my file.txt", "*.txt"), np.arange(6).reshape(2, 3).sum(axis=0))
```

## Python libraries (the Python bridge)

A stub whose first line is `# python: MODULE` makes its declarations calls into the real
Python module, through CPython embedded in the program (PyO3; runtime feature
`pyrt-python`). The stub types the module for rupy; values convert both ways (int, float,
bool, str, None, list, dict, tuple, numpy arrays, and `Object`, an opaque Python object).
A default written `...` leaves the argument out, so Python's default applies. Every call may
raise, and Python's exceptions keep their names. Classes of the stub are Python objects
with their methods, properties, operators and static methods.

```python
# rupylib/statistics.pyi
# python: statistics
def mean(data: list[float] | list[int]) -> float: ...
```

`rupy stub --python MODULE [-o FILE]` drafts a stub with `inspect` (default
`rupylib/MODULE.pyi`); unannotated parameters take the type of their default, anything else
unknown is `Object`, which accepts any value. Stubs are found next to the program in
`rupylib/`, in `./rupylib`, in `RUPY_LIB` and in `src/lib/` (which has
`matplotlib` and `matplotlib.pyplot`). The program links the first Python that imports
its modules (`RUPY_PYTHON`, else python3.14 / 3.13 / 3.12 / python3) and runs with its
packages, so that Python must be installed where the program runs.

## WebAssembly

`rupy wasm FILE.py [-o OUT.wasm]` compiles a program straight to WebAssembly, without
Rust: a WasmGC module (GC structs and arrays for objects, lists, dicts, sets, tuples and
strings; wasm exceptions for Python's) plus `rupy_wasm.mjs`, the JavaScript host that
runs it in a browser (`run(bytes, {stdout, stderr, stdin})`) or with Node.js 22+
(`node rupy_wasm.mjs OUT.wasm`). `rupy wasm --run FILE.py` compiles and runs.
`rupy test --wasm` compares the programs that compile with CPython.

The translator itself builds for `wasm32-unknown-unknown` (`examples/rupy_wasm.rs`, a C
interface: `alloc`, `compile`, `out_ptr`, `out_len`), so `web/` is a playground that
compiles rupy in the browser: `sh web/build.sh`, then serve `web/` over HTTP.

**Packages implemented in Rust** (numpy, sklearn, gymnasium, torch, `rupy.json`, `shlex`,
`fnmatch`, `html`) run in their own wasm module, `rupy_lib.wasm`, built once by
`rupy wasm-lib [-o OUT]` (cargo and the `wasm32-unknown-unknown` target; `rupy wasm`
builds it when a program needs it and puts it next to the host). A program holds no
package code: each package function it calls sends its arguments to the host as tokens
(numbers, strings; lists as their length and items) and reads its result back; package
objects stay in `rupy_lib.wasm`, which the program refers to by handle. The dispatcher of
`rupy_lib.wasm` is generated from the package stubs (`src/wasm/bridge.rs`): for each
function rupy translates a one-line Python wrapper, so it calls the package exactly as a
translated program does. A package object is freed when it was a temporary argument of
another package call, when a variable that only held such objects gets a new one, or
otherwise when the GC collects it after the program ends its run. The host loads
`rupy_lib.wasm` (from `io.lib`, else next to `rupy_wasm.mjs`) only for programs that
use packages.

A known difference: `log`, `exp` and the other transcendental functions of the wasm
backend (JavaScript's `Math` for programs, Rust's libm for `rupy_lib.wasm`) are not
correctly rounded, so a result can differ from CPython's in the last bit (`math.log(3)`
is `1.0986122886681096`, not `...098`). A corpus program that shows it is marked
`# wasm: skip (reason)`, and `rupy test --wasm` counts it with the unsupported ones.

Not yet supported by the wasm backend: generators, functions as values (lambdas work as
`key=` arguments), `nonlocal`, files, `re`, `heapq`, `itertools`, `random`, exception
fields, and `ruai.plot`.

## Rust crates

`from rust.CRATE import Name` uses a Rust crate. Its declarations come from a stub,
`CRATE.pyi`, looked up in `./stubs`, `PY2RS_STUBS` and the stubs shipped with py2rs
(`stubs/regex.pyi`). The crate becomes a Cargo dependency of the generated project.

```python
from rust.regex import Regex

date = Regex.new(r"(\d{4})-(\d{2})-(\d{2})")      # Result → ValueError when invalid
print(date.replace_all("on 2024-05-17", "$3/$2/$1"))
```

A stub is a Python file of typed declarations; each maps to a Rust path or an expression
template (`@rust("{self}.find({0}).map(|m| m.as_str().to_string())")`). `rupy stub
CRATE[@VERSION]` writes one from the crate's rustdoc JSON. `from rust import inline` is
the escape hatch: `inline("xs.sort_unstable();")`, `inline[int]("n.count_ones() as i64")`.

## Python extension modules

`rupy pyo3 mod.py` builds `mod.so`, which Python imports like the original module. Its
module-level functions are exported (int, float, bool, str, list, tuple, dict and
`None` arguments and results); an exception they raise is raised in Python with the same
class; `print` writes to Python's `sys.stdout`. `tests/pyo3/run.sh` checks that importing
the module prints what importing the Python file prints.

## Examples: packages, and `ruai agent`

### rupy with numpy

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

In rupy, `import numpy as np` is a subset of NumPy written in Rust (`src/pyrt/lib/numpy/`): float64 / float32 / int64 / bool arrays, NumPy 2's type promotion and broadcasting, slices that are views sharing memory, boolean masks and index arrays, reductions over axes (`sum` adds in NumPy's pairwise order), `linalg`, and `random.default_rng` bit for bit as NumPy; `print` / `repr` match NumPy's `arrayprint` character for character. Under CPython the same program runs the real NumPy, and `tests/corpus/numpy/` compares them. Because rupy is statically typed: `a[i]` and reductions give 0-d arrays (NumPy scalars), so write `float(a.sum())` where a Python float is needed; `a.shape` can be indexed but not unpacked; dtypes are strings (`dtype="int64"`). Floating-point matrix products add in order and may differ from NumPy's BLAS in the last bit.

### rupy with scikit-learn

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

In rupy, `from sklearn.X import Y` is a subset of scikit-learn in Rust, on the numpy arrays (`src/pyrt/lib/sklearn/`): `LinearRegression`, `Ridge`, `LogisticRegression`, `KNeighborsClassifier` / `Regressor`, `GaussianNB`, `KMeans`, `PCA`, `StandardScaler`, `MinMaxScaler`, `train_test_split`, the common metrics and `load_iris`. The algorithms follow scikit-learn (the same centering, the solvers' optimum, PCA's sign convention, and `train_test_split` with the same `RandomState` numbers, so splits are identical); `tests/corpus/sklearn/` compares the output with scikit-learn. Differences: iterative solvers that scikit-learn stops early (lbfgs) agree to their tolerance; k-NN may pick another neighbor when distances tie exactly; `KMeans` needs its initial centers (`init=array`); `target_names` is a list.

### rupy with Gymnasium and PyTorch

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

`import gymnasium as gym` is `ruai::world`'s environments with Gymnasium's Python API (observations are float32 numpy arrays, bit for bit as Gymnasium's). `import torch` is a subset of PyTorch on ruai's nn engine: autograd, `nn.Linear` and other modules, `nn.Sequential`, losses, `optim.SGD` / `Adam`, `torch.no_grad()`. `torch.manual_seed` reproduces PyTorch's random number generator (MT19937), so `rand`, `randn` and `nn.Linear`'s initial weights are PyTorch's; tensors and modules print as in PyTorch. `tests/corpus/gymnasium/` and `tests/corpus/torch/` compare with Gymnasium and PyTorch (training loops agree at PyTorch's default 4 decimals). Differences: models are `nn.Sequential` or plain classes holding layers (subclassing `nn.Module` is not supported) and `parameters()` returns a list; dtypes are strings in rupy; matrix products and element functions may differ from PyTorch's BLAS / vectorized code in the last bit.

### LLM agent teams (`ruai agent`)

```bash
ruai agent init                                   # create .agge/ here (settings, agents, graphs, logs)
ruai agent model add glm nvidia z-ai/glm-5.3-flash   # providers: openai, nvidia, openrouter, deepseek, groq, gemini, ollama, lmstudio, anthropic
ruai agent chat --team code                       # talk to the lead, who delegates (<delegate>) to architect / coder / tester / reviewer
ruai agent ask -y "create hello.py and run it"    # one task: the agent calls tools by text tags (read/write files, search, shell)
ruai agent book "Git for beginners" --chapters 3 -o gitBook   # outline → chapters (a map node) → editor
ruai agent run brainstorm "how to design a cache layer" -M merge=claude
```

`ruai agent` is [agge](src/agent/README.md) (about 2,500 lines of Python) rewritten in rupy, translated to Rust and built into the `ruai-agent` binary (`cargo install rupy`; ruai runs `ruai-agent` for `ruai agent`), so it needs neither Python nor cargo. The same sources (`src/agent/*.py`) run directly under CPython; `tests/agent.rs` runs the same commands on both (also against a fake OpenAI / Anthropic streaming server) and requires identical output, and checks that the embedded translation `src/agent/agent_gen.rs` is up to date. Differences from the original: parallel delegations, graph nodes and map items run one after another; the chat has no readline history or completion.

## Testing

`rupy test [FILES|DIRS]` (default `tests/`) translates every program, builds them all
in one Cargo package and compares stdout, exit code and exception type with CPython
(`PY2RS_PYTHON`, else python3.14 / 3.13 / 3.12); a program that imports numpy, sklearn,
gymnasium, torch, ruai.plot (matplotlib) or a bridged module runs on the first of those (or `python3`) that has them, and is skipped
when none does. Input comes from `NAME.in` if present. A program whose first line is
`# error: TEXT` must be rejected with a message containing TEXT (`tests/err/`). The corpus
has about 260 programs and 46 rejections; `rupy fuzz` adds random programs.

## Layout

- `src/front.rs` (+ `src/front/`): ruff parser AST → typed IR (`src/ir.rs`); the
  standard library, `re`, operator methods, nested functions, `match`, generics
- `src/own.rs`: ownership inference, liveness, aliasing and iteration checks, views
- `src/exc.rs`: which exceptions can be caught where, so which functions return `Result`
- `src/gen.rs` (+ `src/gen/`): IR → Rust
- `src/modules.rs`: programs of several files; `src/pyo3.rs`: extension modules
- `pyrt/`: runtime: Python printing, format specs, `//` `%` `**` semantics, `str`
  methods by character, exceptions, the standard library, generators, buffered output
