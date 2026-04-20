// Copyright (c) 2026 VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0
//
// GIL-free, process-local `log::Log` implementation used in place of
// `pyo3_log::init()`.
//
// Why: `pyo3_log` forwards every Rust `log` record into the Python `logging`
// module. Under `magnum-conductor`, `oslo.log` replaces logging-handler locks
// with `oslo_log.pipe_mutex.PipeMutex`, whose `acquire()` issues `os.read()`.
// With `eventlet.monkey_patch()` in effect that resolves to the green
// `eventlet.green.os.read`, which in turn calls `eventlet.hubs.trampoline()`
// → `get_hub()`. `get_hub()` is thread-local, so every thread that touches
// Python logging for the first time ends up constructing a fresh eventlet
// hub, which calls `epoll_create1()` and retains that FD indefinitely (the
// hub is stored in a `threading.local` that is never torn down).
//
// Under load, the Rust runtime drives HTTP traffic to the Kubernetes API
// server from many `tokio-rt-worker` threads. Crates like `kube`, `hyper`
// and `rustls` emit `debug!`/`trace!` records prolifically. With
// `pyo3_log` installed, every one of those workers eventually creates an
// eventlet hub and leaks its epoll FD. Over hours/days the
// `magnum-conductor` process exhausts its open-file limit and fails with
// "Too many open files" (see
// <https://github.com/vexxhost/magnum-cluster-api/issues/822>).
//
// Writing directly to stderr sidesteps the whole chain: no GIL acquisition
// from tokio workers, no Python `logging` module, no `PipeMutex`, no
// eventlet hub, no epoll leak. Operators still get the log lines because
// `oslo.log` / systemd / Kolla's log shipper already capture the
// conductor's stderr stream.

use log::{LevelFilter, Log, Metadata, Record};
use std::io::{self, Write};
use std::sync::Mutex;

struct StderrLogger {
    level: LevelFilter,
    lock: Mutex<()>,
}

impl Log for StderrLogger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= self.level
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }

        // Serialize writes so interleaved records from different threads do
        // not tear. Recover from a poisoned mutex rather than panicking: a
        // prior panic inside a logger call site would otherwise take down
        // every subsequent logger invocation in the process.
        let _guard = match self.lock.lock() {
            Ok(g) => g,
            Err(poisoned) => poisoned.into_inner(),
        };

        // We deliberately ignore write errors: there is nothing sensible we
        // can do if stderr is closed, and panicking inside a logger would be
        // much worse than dropping a log line.
        let _ = writeln!(
            io::stderr(),
            "[{} {}] {}",
            record.level(),
            record.target(),
            record.args(),
        );
    }

    fn flush(&self) {
        let _ = io::stderr().flush();
    }
}

/// Parse `RUST_LOG` into a single [`LevelFilter`].
///
/// This intentionally does not implement the full `env_logger` filter
/// language (per-module filters, regex matches, ...). All we need in
/// production is a global level knob, and keeping the parser tiny avoids
/// pulling in an extra dependency just to replace three lines of
/// functionality.
fn level_from_env() -> LevelFilter {
    match std::env::var("RUST_LOG") {
        Ok(value) => value
            .trim()
            .parse::<LevelFilter>()
            .unwrap_or(LevelFilter::Warn),
        Err(_) => LevelFilter::Warn,
    }
}

/// Install the stderr logger as the global `log` sink.
///
/// Idempotent: if another component has already installed a logger (for
/// example when the extension module is imported twice in the same
/// interpreter, which happens in some test harnesses) we silently leave
/// the existing logger in place.
pub fn init() {
    let level = level_from_env();
    let logger: &'static StderrLogger = Box::leak(Box::new(StderrLogger {
        level,
        lock: Mutex::new(()),
    }));

    if log::set_logger(logger).is_ok() {
        log::set_max_level(level);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use log::Level;

    #[test]
    fn stderr_logger_respects_level() {
        let logger = StderrLogger {
            level: LevelFilter::Warn,
            lock: Mutex::new(()),
        };

        assert!(logger.enabled(&Metadata::builder().level(Level::Error).build()));
        assert!(logger.enabled(&Metadata::builder().level(Level::Warn).build()));
        assert!(!logger.enabled(&Metadata::builder().level(Level::Info).build()));
        assert!(!logger.enabled(&Metadata::builder().level(Level::Debug).build()));
    }

    #[test]
    fn level_from_env_defaults_to_warn_on_missing_or_invalid() {
        // The environment may or may not have RUST_LOG set depending on how
        // the test binary is invoked; exercise both explicit branches.
        std::env::remove_var("RUST_LOG");
        assert_eq!(level_from_env(), LevelFilter::Warn);

        std::env::set_var("RUST_LOG", "not-a-level");
        assert_eq!(level_from_env(), LevelFilter::Warn);

        std::env::set_var("RUST_LOG", "debug");
        assert_eq!(level_from_env(), LevelFilter::Debug);

        std::env::remove_var("RUST_LOG");
    }
}
