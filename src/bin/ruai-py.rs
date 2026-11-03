//! `ruai-py`: `ruai py ARGS...` runs it (ruai runs `ruai-NAME` from PATH for
//! the commands it does not have), so the old command keeps working.

#[path = "../cli.rs"]
mod cli;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    std::process::exit(cli::main(&args));
}
