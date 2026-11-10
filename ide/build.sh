#!/bin/sh
# Build the rupy IDE's assets: the compiler (rupy.wasm), the host of compiled
# programs (rupy_wasm.mjs) and the Rust packages (rupy_lib.wasm), from
# web/build.sh, copied to public/rupy/. Then run it on rucloud:
#   sh ide/build.sh && rucloud dev ide
# `--skip-cargo` copies what web/ already has.
set -e
cd "$(dirname "$0")/.."
if [ "$1" != "--skip-cargo" ] || [ ! -f web/rupy.wasm ]; then
  sh web/build.sh
fi
mkdir -p ide/public/rupy
cp web/rupy.wasm web/rupy_lib.wasm web/rupy_wasm.mjs ide/public/rupy/
ls -l ide/public/rupy
