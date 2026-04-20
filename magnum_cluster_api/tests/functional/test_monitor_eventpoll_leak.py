# Copyright (c) 2026 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Regression test for the eventpoll FD leak in issue #822.

This is the follow-up to PR #985. PR #985 fixed a real, separate leak in
the ``hyper_util`` connection pool by sharing a single ``kube::Client``
across all Rust entry points; its existing regression test
(``test_monitor_fd_leak.py``) continues to guard against that leak by
counting ``socket:[...]`` entries in ``/proc/self/fd``.

The leak this test covers is *different* and was root-caused by
@gabriel-samfira in the comments under
https://github.com/vexxhost/magnum-cluster-api/issues/822:

    Rust `log` record
      → pyo3_log forwards into Python `logging`
      → oslo.log swaps the handler lock for `oslo_log.pipe_mutex.PipeMutex`
      → `PipeMutex.acquire()` calls `os.read()`
      → eventlet.monkey_patch() makes that the *green* `os.read`
      → `eventlet.hubs.trampoline()` → `get_hub()`
      → per-thread `Hub.__init__` runs `select.epoll()` → epoll_create1()

Because ``get_hub()`` is thread-local and the created hub is never torn
down when the thread exits, every distinct thread that touches Python
logging leaks one ``anon_inode:[eventpoll]`` FD. Under
``magnum-conductor`` load this manifests as unbounded FD growth and
eventually "Too many open files".

The fix in this repository replaces ``pyo3_log::init()`` with a
GIL-free stderr logger (``src/logging.rs``), so Rust log records never
flow through Python ``logging``. That breaks the chain at step 1 and
keeps the eventpoll FD count bounded to whatever the conductor and
eventlet itself legitimately need (typically 1-3).

The test runs in a *subprocess* because ``eventlet.monkey_patch()`` is a
process-wide, irreversible change to the standard library. Running
it inline would silently corrupt every other test sharing the same
interpreter.
"""

import os
import subprocess
import sys
import textwrap

import pytest

pytestmark = [
    pytest.mark.skipif(
        sys.platform != "linux",
        reason="eventpoll FDs are a Linux-specific artifact of epoll_create1",
    ),
    pytest.mark.skipif(
        not os.path.isdir("/proc/self/fd"),
        reason="/proc/self/fd is not available in this environment",
    ),
]


# The subprocess body. Kept as a string so the parent test process stays
# completely untouched by ``eventlet.monkey_patch()``.
_SUBPROCESS_SCRIPT = textwrap.dedent('''
    import os
    import sys
    import threading

    # 1. Reproduce the production setup: eventlet first, *before* any stdlib
    #    module that would otherwise be patched in-place.
    import eventlet
    eventlet.monkey_patch()

    # 2. Bring oslo.log online with the same PipeMutex workaround that
    #    magnum-conductor uses in production. Set the root level to DEBUG
    #    so Rust log records from kube/hyper/rustls actually propagate.
    #
    #    ``log_file`` is set on purpose: oslo.log only swaps logging-handler
    #    locks for ``PipeMutex`` when a file-based handler is attached, and
    #    it is precisely ``PipeMutex.acquire() -> os.read()`` that triggers
    #    the eventlet hub creation on each new thread. Without a log_file
    #    the pre-fix code does *not* leak, and the regression this test
    #    guards against would go undetected.
    import tempfile
    log_file = os.path.join(tempfile.gettempdir(), "mcapi-eventpoll-probe.log")

    from oslo_config import cfg
    from oslo_log import log as logging

    CONF = cfg.CONF
    logging.register_options(CONF)
    CONF([], project="magnum", default_config_files=[])
    CONF.set_override("debug", True)
    CONF.set_override("log_file", log_file)
    CONF.set_override(
        "default_log_levels",
        [
            "magnum_cluster_api=DEBUG",
            "kube=DEBUG",
            "hyper=DEBUG",
            "rustls=DEBUG",
            "tower=DEBUG",
        ],
    )
    logging.setup(CONF, "magnum")

    # 3. Importing the native extension triggers the logger initialiser
    #    at src/lib.rs. Pre-fix this was pyo3_log::init(), post-fix it is
    #    our GIL-free stderr logger.
    from magnum_cluster_api.magnum_cluster_api import Monitor as RustMonitor


    def count_eventpoll_fds() -> int:
        n = 0
        for fd in os.listdir("/proc/self/fd"):
            try:
                link = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                continue
            if "eventpoll" in link:
                n += 1
        return n


    class _FakeTemplate:
        network_driver = "calico"


    class _FakeCluster:
        """Enough of a Magnum Cluster to let RustMonitor issue Kube API calls."""

        def __init__(self, stack_id):
            self.uuid = "00000000-0000-0000-0000-000000000000"
            self.cluster_template = _FakeTemplate()
            self.stack_id = stack_id
            self.labels = {"kube_tag": "v1.30.0"}
            self.status = "CREATE_COMPLETE"


    def poll_once():
        try:
            RustMonitor(_FakeCluster("eventpoll-leak-test")).poll_health_status()
        except Exception:
            # Expected: FakeCluster has no KubeadmControlPlane in the real
            # cluster, so poll_health_status() raises. By that point the
            # Kube API request has been issued and any logging side effects
            # (and their eventpoll leak) have already occurred.
            pass


    # 4. Warm-up: the first few calls legitimately create a hub for the
    #    main thread / the tokio workers; exclude those from the baseline.
    for _ in range(5):
        poll_once()

    baseline = count_eventpoll_fds()

    # 5. Load generator: use distinct native threads, one per iteration,
    #    each of which creates its own RustMonitor and polls. This matches
    #    the production pattern where separate conductor worker threads
    #    service different clusters. With pyo3_log the Rust log records
    #    emitted from tokio-rt-workers during those calls inevitably
    #    traverse Python logging and create a fresh eventlet hub +
    #    epoll FD per thread that has never logged before.
    iterations = 50
    peak = baseline
    for i in range(iterations):
        t = threading.Thread(target=poll_once, name=f"mcapi-eventpoll-{i}")
        t.start()
        t.join()
        peak = max(peak, count_eventpoll_fds())

    leaked = peak - baseline
    print(f"baseline={baseline} peak={peak} leaked={leaked}", flush=True)

    # Communicate the result to the parent via exit code; 0 = under the
    # threshold, 1 = leak detected. The parent asserts on the exit code so
    # the test harness surfaces the result in the normal pytest way.
    sys.exit(0 if leaked < 10 else 1)
    ''')


def test_rust_log_does_not_leak_eventpoll_fds(tmp_path):
    """A fresh native thread touching the Rust entry point must not leak epolls.

    Pre-fix (``pyo3_log::init()`` installed): every thread that triggers a
    Rust ``log`` record gets an eventlet hub with its own epoll FD, and the
    FD is retained after the thread exits. Over ``iterations`` threads this
    accumulates to tens of leaked FDs.

    Post-fix (GIL-free stderr logger): Rust log records never enter Python
    ``logging``, so no eventlet hub is ever created on behalf of the Rust
    side, and the eventpoll FD count stays within a handful of
    hub/selector FDs that eventlet and the test harness legitimately own.
    """
    if not os.environ.get("KUBECONFIG"):
        pytest.skip("KUBECONFIG must be set to a real Kubernetes API server")

    script_path = tmp_path / "eventpoll_leak_probe.py"
    script_path.write_text(_SUBPROCESS_SCRIPT)

    # Inherit KUBECONFIG (and everything else) so the subprocess can talk
    # to the same cluster used by the broader functional test suite.
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Surface the probe's own diagnostics on failure.
    diagnostics = (
        f"stdout:\n{result.stdout}\nstderr (tail):\n"
        f"{result.stderr[-2000:] if result.stderr else ''}"
    )
    assert result.returncode == 0, (
        "eventpoll FD leak detected — see "
        "https://github.com/vexxhost/magnum-cluster-api/issues/822\n"
        f"{diagnostics}"
    )
