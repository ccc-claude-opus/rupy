//! The `rupy` command: run, check, emit, build, compile to WebAssembly and
//! test rupy programs.

mod cli;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    std::process::exit(cli::main(&args));
}
