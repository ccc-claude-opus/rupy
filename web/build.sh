#!/bin/sh
# Build the rupy playground: the compiler as WebAssembly (rupy.wasm), the
# host of compiled programs (rupy_wasm.mjs), and the packages implemented in
# Rust for them (rupy_lib.wasm: numpy, sklearn, torch, ...). Serve the
# directory over HTTP:
#   sh web/build.sh && python3 -m http.server -d web 8000
set -e
cd "$(dirname "$0")/.."
cargo build --release --example rupy_wasm --target wasm32-unknown-unknown --no-default-features --features translator
cp target/wasm32-unknown-unknown/release/examples/rupy_wasm.wasm web/rupy.wasm
cp src/wasm/host.mjs web/rupy_wasm.mjs
cargo run --release --quiet --bin rupy -- wasm-lib -o web/rupy_lib.wasm
ls -l web/rupy.wasm web/rupy_lib.wasm
