# Changelog

## 0.2.0

- An int that went into a float place (`x: float = 3`, `f(3)` for a float parameter, `[1, 2]`
  as `list[float]`) and is then printed is rejected: CPython prints `3`, rupy `3.0`. The new
  `intfloat` pass follows such values per call context; `float(n)` is an explicit float.
- `__init__` with union parameters: one constructor per member (`new`, `new_str`, ...), picked
  by the argument types; `Fraction("1/3")`, `Fraction(0.5)`, `Decimal(5)`, `Decimal(0.1)`.
- An exception raised inside a generator reaches the consumer's `try` (around `for`, `next()`,
  `list()`, a comprehension) on both backends, and ends the generator; user exceptions are
  raised with their class chain.
- `argparse`: the translator types `parse_args()` (a dataclass per parser); the package reads
  the command line, prints usage and help, and errors with exit code 2, as CPython.

- `decimal`, `string` and `textwrap`, written in rupy (`pylib/`): Decimal after `_pydecimal`
  with digit-string coefficients in the default context; textwrap's `wordsep_re` written out by
  hand.
- `operator` (rewritten into expressions and lambdas before lowering), `copy.copy` /
  `copy.deepcopy`, and `enum.Enum` (a frozen dataclass, its generated code written after the
  program); a lambda for an `Optional[Callable]` parameter.

- `datetime` and `pathlib`, written in rupy (`pylib/`). datetime: naive `timedelta`, `date`,
  `time`, `datetime` after CPython's `_pydatetime.py` and C module (timedelta's float arguments
  rounded as `delta_new` does, the C module's error messages), `isoformat` / `fromisoformat`,
  `strftime` and `strptime` (the regex's alternatives in order) in the C locale. pathlib: `Path`
  on POSIX, pure operations and files.
- A union return type of a method pairs with its union parameter; `a + b` uses `b.__radd__`
  when `a.__add__` does not take `b`; a class's names are not seen by its methods when a
  package is renamed; wasm: `time.strftime` from the host, and a package function only reached
  from code never run no longer makes a program unsupported.
- A program's `# python:` stub (`rupylib/datetime.pyi`) comes before rupy's own package of that name.

- `statistics`, `fractions`, `csv` and `io.StringIO`, written in rupy (`pylib/`, built into
  rupy like rstatistics, so both backends). statistics sums exactly with expansions of floats
  (Shewchuk) and rounds once, as CPython does with fractions: `mean`, `variance`, `stdev`,
  `harmonic_mean`, ... give CPython's floats to the last bit; `NormalDist.inv_cdf` uses fused
  multiply-adds like CPython's C version. csv is CPython's `_csv` state machine and writer.
- Methods with union parameters (one overload per member), `isinstance` of an object decided
  statically, a function may return a generator, `TextIO` annotations, `math.nextafter`,
  `math.ulp`; `math.hypot` is CPython's `vector_norm` on both backends (it was libm's /
  JavaScript's).
- A file is a handle that copies share (as in Python), `open(..., newline=...)`, and reading
  translates `\r\n` / `\r` to `\n` as CPython does.
- Fixes: int / int beyond 2**53 is rounded once (it was rounded twice); the repr of a float is
  the nearest of the shortest digits (`1770740270910798.2`, not `.3`); dataclass reprs of a
  package's classes have no `PKG__` prefix.

- `math.gamma`, `lgamma`, `erf`, `erfc`, `asinh`, `acosh`, `atanh` and `math.fsum`, with
  CPython's errors. gamma and lgamma are CPython's own Lanczos code; Apple's clang fuses
  its `a * b + c` into fused multiply-adds, so rupy does too (`mul_add`; a BigInt
  `fmaExact` on wasm), and the Rust backend matches CPython to the last bit. On wasm the
  last digit may differ (JavaScript's exp / pow, FreeBSD's erf): `std_math_special.py` is
  Rust only, `std_math_special12.py` checks 12 digits on both.
- `json.loads` into the declared type: `xs: list[int] = json.loads(s)`, for int, float,
  str, bool, Optional, list and `dict[str, ...]`; CPython's parse errors (ValueError), and
  TypeError for JSON of another type. Both backends.
- Functions as values on the Rust backend: a `Callable` is a `pyrt::Fun<dyn Fn>` (an `Rc` closure),
  so closures can be returned (`make_adder`), kept in lists, dicts and dataclass fields, and
  called directly (`b.on_click(x)`, `pick("add")(2.0, 3.5)`). A lambda that is kept and reads a
  variable assigned more than once (a loop variable) is rejected on both backends: rupy copies
  it when the lambda is made, Python reads it when it is called.
- **rstatistics**, R's probability and statistics functions, in `rstatistics/` (`pip install rstatistics`, pure Python,
  no dependencies): `d`/`p`/`q` of 17 distributions, R's random numbers after `set_seed`
  (Mersenne-Twister, inversion, `sample`), `t_test`, `var_test`, `chisq_test`, `binom_test`,
  `prop_test`, `cor_test`, `summary`, `quantile` (types 1–9), `cor`, `mad`, `fivenum`, ...,
  printed as R prints them (formatReal, `print.htest`). `rstatistics/tests/run.py` compares it with
  R 4.6: printed output identical, distribution functions within a relative 1e-12.
- **rstatistics 0.4.0**: R's graphics, in rstatistics: a device that writes SVG with R's
  layout (`mar = c(5.1, 4.1, 4.1, 2.1)` lines, `mgp = c(3, 1, 0)`, the ranges extended by
  4% at both ends, the ticks of `pretty()`), the primitives (points with the open circle of
  `pch = 1`, lines, segments, rect, polygon, text, axis, box, title, mtext, abline, legend)
  and the plots (`plot`, `hist`, `density`, `boxplot`, `qqnorm`, `qqline`, `ecdf`, `curve`,
  `barplot`); the numbers of the plots come from the calculation layer (`pretty`,
  `hist_stats`, `density_stats`, `ecdf`, `boxplot_stats`, `ppoints`), which agrees with R
  to a relative 1e-12.
- **rstatistics** needs Python 3.13 or newer (`math.fma`, which R's generators use to get
  R's numbers to the last bit); `pip install rstatistics` refuses the older versions.
- **rstatistics 0.3.0**: the linear models of R's stats package: `lm` fits a model with the
  Householder QR of R's `lm.fit` (the column pivoting of `dqrdc2` included, so a rank
  deficient fit drops the collinear coefficients as R does) and the summary of the fit
  prints as `print(summary(lm(...)))` does; `anova` and `aov` give the analysis of
  variance of a model and of a one-way layout, `predict` the predictions of a model
  with the confidence and the prediction intervals.
- **rstatistics 0.2.0**: the random numbers of all the distributions are R's to the last bit
  (Ahrens and Dieter's gamma and exponential, Cheng's beta, the BTPE binomial, the normal
  rejection Poisson, Kachitvichyanukul and Schmeiser's hypergeometric, as R's `src/nmath`
  computes them; R's compiler contracts the floating point expressions, so rupy gained
  `math.fma`); `qnbinom`, `qhyper` and `dnbinom` with a mean; the nonparametric tests of R's
  stats package (`wilcox_test`, `ks_test`, `shapiro_test`, `fisher_test`, `kruskal_test`),
  `p_adjust` and `table`.
- **Packages written in rupy**: `import rstatistics` compiles its source with the program (the
  source is built into rupy), its top-level names renamed so they cannot clash with the
  program's; it works on the Rust and the wasm backends.
- The builtin `format(value, spec)`; `math.log1p`, `math.expm1`, `math.nan`.
- `math.fma(x, y, z)`, the fused multiply-add of Python 3.13, on the Rust and the wasm
  backends: R's compiler contracts its floating point expressions, so the numbers of R's
  generators need it.
- The wasm backend unpacks lists (`a, b = s.split("e")`), with Python's length errors.
- **The wasm backend runs the packages implemented in Rust** (numpy, sklearn, gymnasium,
  torch, `rupy.json`, `shlex`, `fnmatch`, `html`), in browsers too. They are compiled
  once by cargo into `rupy_lib.wasm` (`rupy wasm-lib`), whose dispatcher is generated from
  the package stubs: for each function, rupy translates a Python wrapper, so the call is
  the one a translated program makes. Programs send arguments and read results as tokens
  through the host, and refer to package objects by handle; temporaries and objects of
  variables that get a new one are freed at once, the rest when the GC collects them.
  All 15 programs of the numpy, sklearn, torch and gymnasium corpus match CPython on
  wasm; 247 of the corpus's 270 programs now compile to wasm (221 before) and all match.
- The package stubs are built into rupy, so the compiler in a browser has them.
- `repr()` of strings on the wasm backend escapes what `str.isprintable()` rejects
  (`\xa0`, `\u2028`, ...), like CPython.
- Fixed: `Tensor.ndim` (its stub named a method that does not exist); `rupy test` with no
  arguments looks in `tests/corpus`.
- `np.linalg.det` as NumPy computes it (sign · exp(Σ log |u_ii|)): `det([[1, 2], [3, 4]])` is
  `-2.0000000000000004`, as in NumPy, not `-2.0`.
- A corpus file may say `# wasm: skip (reason)`: `rupy test --wasm` counts it with the
  unsupported programs. Known: transcendental functions on wasm are not correctly rounded.

## 0.1.0

rupy is py0, the typed subset of Python that was `ruai py` in ruai 3.2–4.5, made its own
crate. The language, its packages and their behavior are those of ruai 4.5.0.

- **The crate**: the translator (`rupy::front`, `own`, `gen`, `wasm`, ...; feature
  `translator`, on by default) and the runtime of translated programs (`rupy::pyrt`, always
  built). Translated programs depend on `rupy` with `default-features = false` and only the
  runtime features they use: `re`, `http`, `numpy`, `sklearn`, `gymnasium`, `torch`, `plot`,
  `python` (formerly ruai's `pyrt-*` features).
- **ruai is optional**: only `gymnasium`, `torch` and `plot` (`ruai.plot`) depend on it, for
  its environments, its nn engine and its plots. rupy has its own NumPy-compatible random
  numbers (`rupy::rng`).
- **Commands**: `rupy run / emit / check / explain / build / wasm / test / fuzz / stub / pyo3`
  (formerly `ruai py ...`). `cargo install rupy` also installs `ruai-py` and `ruai-agent`;
  ruai runs `ruai-NAME` for the commands it does not have, so `ruai py ...` and
  `ruai agent ...` keep working.
- **Renamed**: the packages `ruai.http` and `ruai.json` are `rupy.http` and `rupy.json`
  (`ruai.plot` keeps its name). Package stubs are looked up in `rupylib/` and in `RUPY_LIB`,
  the Python bridge's interpreter is `RUPY_PYTHON`, and generated files carry
  `// rupy-python:` lines. The WebAssembly host is `rupy_wasm.mjs`, and the browser
  compiler is the example `rupy_wasm`.
- `ruai agent` (agge written in rupy) is `src/agent/`; its translation is
  `src/agent/agent_gen.rs`.
