# Copyright (c) 2026 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Regression test for https://github.com/vexxhost/magnum-cluster-api/issues/822.

``magnum-conductor`` periodically calls ``Monitor.poll_health_status()`` for
every cluster it knows about. Prior to the fix every call constructed a brand
new ``kube::Client`` (via ``kube::Client::try_default()``), and each such client
owned its own ``hyper_util`` connection pool whose background tokio tasks /
sockets were never reclaimed (see
https://github.com/tokio-rs/tokio/issues/1830). Over time this exhausts the
process file-descriptor limit and magnum-conductor starts failing with
``Too many open files``.

This functional test exercises the real call-path from Python -> Rust against
a live Kubernetes API server and asserts that the number of open socket file
descriptors does not grow unbounded with the number of ``Monitor`` instances
created.

The test is skipped when ``KUBECONFIG`` is not set (i.e. during the plain
``unit`` test suite). It is intended to run in the ``functional`` environment
which points at a real cluster.
"""
import os

import pytest

# Match production: magnum-conductor is an eventlet app and invokes
# ``RustMonitor`` through ``eventlet.tpool`` (see magnum_cluster_api/monitor.py).
# The kube::Client construction / drop leak only manifests when each
# invocation happens on a distinct native thread, which is exactly what
# ``tpool.Proxy`` arranges.
import eventlet  # noqa: E402  -- must be imported before magnum_cluster_api

eventlet.monkey_patch()
from eventlet import tpool  # noqa: E402

from magnum_cluster_api.magnum_cluster_api import Monitor as RustMonitor  # noqa: E402


pytestmark = pytest.mark.skipif(
    not os.environ.get("KUBECONFIG"),
    reason="KUBECONFIG must be set to a real Kubernetes API server",
)


class _FakeClusterTemplate:
    network_driver = "calico"


class _FakeCluster:
    """Minimal stand-in for a Magnum Cluster object.

    Only the fields accessed by ``magnum::Cluster::FromPyObject`` are
    populated, which is enough to construct a ``RustMonitor`` and trigger
    ``poll_health_status``.
    """

    def __init__(self, stack_id: str) -> None:
        self.uuid = "00000000-0000-0000-0000-000000000000"
        self.cluster_template = _FakeClusterTemplate()
        # A non-None stack_id forces poll_health_status to issue real Kube API
        # requests (list Machines / KubeadmControlPlane), which is exactly
        # what the connection-pool leak requires to manifest.
        self.stack_id = stack_id
        # kube_tag has no default on the Rust side so we have to supply it.
        self.labels = {"kube_tag": "v1.30.0"}
        self.status = "CREATE_COMPLETE"


def _count_open_sockets() -> int:
    """Return the number of ``socket:[...]`` entries in ``/proc/self/fd``."""
    count = 0
    for fd in os.listdir("/proc/self/fd"):
        try:
            link = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            # fd was closed between listdir and readlink; ignore.
            continue
        if link.startswith("socket:"):
            count += 1
    return count


def _poll_once(stack_id: str) -> None:
    # ``tpool.Proxy`` runs method calls on a native-thread pool, exactly like
    # ``magnum_cluster_api.monitor.Monitor.poll_health_status`` does in
    # production.
    monitor = tpool.Proxy(RustMonitor(_FakeCluster(stack_id)))
    try:
        monitor.poll_health_status()
    except Exception:
        # The fake cluster doesn't have a real KubeadmControlPlane, so
        # poll_health_status raises ``NoKubeadmControlPlane``. That's fine:
        # by that point the Kube API requests have already been issued and
        # any leaked connections are now pinned on the leaked client.
        pass


def test_monitor_does_not_leak_kube_client_sockets() -> None:
    """Creating many Monitors must not cause unbounded socket growth.

    With the bug present, each ``RustMonitor(cluster)`` constructs a fresh
    ``kube::Client`` whose connection pool retains a handful of sockets even
    after the Python object is garbage collected. Over ``iterations`` runs
    that accumulates to tens-to-hundreds of sockets, providing a reliable
    signal that the client is being recreated instead of reused.
    """
    iterations = 200

    # Warm-up: first-time client construction plus TLS handshake allocate
    # some connections; exclude them from the baseline.
    for _ in range(10):
        _poll_once("warmup")

    baseline = _count_open_sockets()

    peak = baseline
    for i in range(iterations):
        _poll_once("leak-test")
        # Sample after every iteration so we catch the peak even if the
        # tokio connection pool later reclaims some sockets.
        peak = max(peak, _count_open_sockets())

    leaked = peak - baseline

    # With the singleton-client fix in place, the same connection pool is
    # reused for every Monitor instance; ``leaked`` stays within the small
    # pool size (typically 0-4 extra sockets). Without the fix the counter
    # climbs to many tens of sockets over 200 iterations. The threshold
    # below splits those two regimes with plenty of headroom.
    assert leaked < 20, (
        f"kube::Client socket leak detected: {leaked} extra sockets after "
        f"{iterations} Monitor() invocations (baseline={baseline}, peak={peak}). "
        f"See https://github.com/vexxhost/magnum-cluster-api/issues/822"
    )
