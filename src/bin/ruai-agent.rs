//! `ruai-agent`: teams of LLM agents (agge), run as `ruai agent ARGS...` (ruai
//! runs `ruai-NAME` from PATH for the commands it does not have). The program
//! is written in rupy (`src/agent/*.py`, which CPython runs too) and translated
//! to Rust by `rupy emit src/agent/agent.py --module` into
//! `src/agent/agent_gen.rs`; the test `tests/agent.rs` checks that the
//! translation is up to date.

#[allow(clippy::all)]
#[path = "../agent/agent_gen.rs"]
mod agent_gen;

fn main() {
    let argv = std::iter::once("ruai agent".to_string()).chain(std::env::args().skip(1)).collect();
    rupy::pyrt::stdlib::set_argv(argv);
    agent_gen::main();
}
