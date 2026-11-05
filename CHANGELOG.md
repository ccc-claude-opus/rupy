# Changelog

## Unreleased

- **The wasm backend runs the packages implemented in Rust** (numpy, sklearn, gymnasium,
  torch, `rupy.json`, `shlex`, `fnmatch`, `html`), in browsers too. They are compiled
  once by cargo into `rupy_lib.wasm` (`rupy wasm-lib`), whose dispatcher is generated from
  the package stubs: for each function, rupy translates a Python wrapper, so the call is
  the one a translated program makes. Programs send arguments and read results as tokens
  through the host, and refer to package objects by handle; temporaries and objects of
  variables that get a new one are freed at once, the rest when the GC collects them.
  All 15 programs of the numpy, sklearn, torch and gymnasium corpus match CPython on
  wasm; 241 of the corpus's 263 programs now compile to wasm (221 before) and all match.
- The package stubs are built into rupy, so the compiler in a browser has them.
- `repr()` of strings on the wasm backend escapes what `str.isprintable()` rejects
  (`\xa0`, `\u2028`, ...), like CPython.
- Fixed: `Tensor.ndim` (its stub named a method that does not exist); `rupy test` with no
  arguments looks in `tests/corpus`.

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
