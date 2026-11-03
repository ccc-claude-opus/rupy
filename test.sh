#!/usr/bin/env bash
# Run rupy's tests: one group, or all of them, with a summary at the end.
#   ./test.sh <group> [more groups...]
#
#   corpus         every program of tests/corpus against CPython (Rust and WebAssembly backends)
#   wasm           only the WebAssembly backend's corpus run
#   pyo3           rupy → a Python extension module, against CPython
#   agent          ruai-agent against CPython running the same rupy sources
#   check          build with each runtime package alone, and the compiler for wasm32
#   lint           clippy (warnings are errors) and rustdoc
#   file NAME [FILTER]   one test file (tests/NAME.rs), optionally only matching tests
#   ci             what CI runs
#   all            every group
#   deps           show which tools and Python packages the tests need
#
# The reference is CPython 3.14 (PY2RS_PYTHON, else python3.14 / 3.13 / 3.12).
# rupy's gymnasium, torch and ruai.plot packages build ruai from ../ruai.
set -u
cd "$(dirname "$0")"

PYTHON="${PY2RS_PYTHON:-python3.14}"
RESULTS=()
FAILED=0

step() {
  local name="$1"
  shift
  printf '\n\033[1m==> %s\033[0m\n$ %s\n' "$name" "$*"
  local t0=$SECONDS
  if "$@"; then
    RESULTS+=("ok    $(printf '%4ss' $((SECONDS - t0)))  $name")
  else
    RESULTS+=("FAIL  $(printf '%4ss' $((SECONDS - t0)))  $name")
    FAILED=$((FAILED + 1))
  fi
}

usage() {
  sed -n '2,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
}

group() {
  case "$1" in
    corpus) step "corpus (Rust and wasm) against CPython" cargo test --release --test rupy ;;
    wasm) step "WebAssembly corpus against CPython" cargo test --release --test rupy wasm_corpus_matches_cpython ;;
    pyo3)
      step "build rupy" cargo build --release
      step "PyO3 module against CPython" env PY2RS_PYTHON="$PYTHON" sh tests/corpus/pyo3/run.sh
      ;;
    agent) step "ruai-agent against CPython" cargo test --release --test agent ;;
    check)
      step "runtime only" cargo check --lib --no-default-features
      for f in re http numpy sklearn gymnasium torch plot python translator; do
        step "feature $f alone" cargo check --lib --no-default-features --features "$f"
      done
      step "compiler for wasm32" cargo build --release --example rupy_wasm --target wasm32-unknown-unknown --no-default-features --features translator
      ;;
    lint)
      step "clippy" cargo clippy --all-targets --features "numpy sklearn gymnasium torch plot" -- -D warnings
      step "rustdoc" env RUSTDOCFLAGS="-D warnings" cargo doc --no-deps --features "numpy sklearn gymnasium torch plot"
      ;;
    ci | all)
      step "cargo test" cargo test --release
      group pyo3
      group check
      group lint
      ;;
    deps)
      for t in cargo node "$PYTHON"; do
        if command -v "$t" >/dev/null 2>&1; then echo "ok       $t"; else echo "missing  $t"; fi
      done
      for m in numpy gymnasium sklearn matplotlib torch; do
        if "$PYTHON" -c "import $m" 2>/dev/null; then echo "ok       python: $m"; else echo "missing  python: $m (pip install ${m/sklearn/scikit-learn})"; fi
      done
      if [ -f ../ruai/Cargo.toml ]; then echo "ok       ../ruai"; else echo "missing  ../ruai (git clone https://github.com/ccc-llm/ruai)"; fi
      ;;
    *)
      echo "unknown group: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
}

if [ $# -eq 0 ] || [ "$1" = help ] || [ "$1" = -h ] || [ "$1" = --help ]; then
  usage
  exit 0
fi

if [ "$1" = file ]; then
  [ $# -ge 2 ] || { echo "usage: ./test.sh file NAME [FILTER]" >&2; exit 2; }
  step "tests/$2.rs${3:+ ($3)}" cargo test --release --test "$2" ${3:+"$3"}
else
  for g in "$@"; do
    [ "$g" = deps ] && { group deps; exit 0; }
    group "$g"
  done
fi

printf '\n\033[1m==> summary\033[0m\n'
printf '%s\n' "${RESULTS[@]}"
if [ "$FAILED" -gt 0 ]; then
  printf '%d step(s) failed\n' "$FAILED"
  exit 1
fi
