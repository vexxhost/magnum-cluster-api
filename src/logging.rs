// Copyright (c) 2026 VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0
//
// Initialise a GIL-free `log` sink for the Rust side of the extension.
//
// Why not `pyo3_log`:
// ====================
//
// `pyo3_log::init()` forwards every Rust `log` record into the Python
// `logging` module. Under `magnum-conductor`, `oslo.log` swaps the
// logging-handler lock for `oslo_log.pipe_mutex.PipeMutex`, whose
// `acquire()` calls `os.read()`. With `eventlet.monkey_patch()` in
// effect that resolves to the green `eventlet.green.os.read`, which
// calls `eventlet.hubs.trampoline()` → `get_hub()`. `get_hub()` is
// thread-local, so the first Rust log record emitted from any new
// native thread (including every `tokio-rt-worker`) constructs a fresh
// eventlet `Hub` whose `select.epoll()` allocates an
// `anon_inode:[eventpoll]` FD. The hub is stored in a `threading.local`
// that is never torn down when the thread exits, so the FD leaks
// permanently. See <https://github.com/vexxhost/magnum-cluster-api/issues/822>
// for the full diagnosis by @gabriel-samfira.
//
// The fix is simply to stop routing Rust log records through Python
// `logging`. `env_logger` is the canonical crate for this: it writes
// formatted records directly to stderr, honours `RUST_LOG`, never
// touches the GIL, and is maintained by the `rust-lang` org so we do
// not have to own the code. `magnum-conductor`'s existing stderr
// capture (oslo.log + systemd / Kolla's log shipper) picks the output
// up transparently, so no observability is lost.

/// Install `env_logger` as the global `log` sink.
///
/// Idempotent: if a logger has already been installed (for example if
/// the extension module is imported more than once into the same
/// interpreter, which happens in some test harnesses), this is a
/// no-op and the pre-existing logger is left in place.
pub fn init() {
    // `try_init` is the non-panicking variant — it returns `Err` if a
    // global logger is already set, which is exactly the idempotent
    // behaviour we want. Defaulting the filter to `warn` keeps the
    // stderr stream quiet in production while still allowing operators
    // to turn the verbosity up with `RUST_LOG=debug` etc.
    let _ = env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("warn"))
        .try_init();
}
