# Copyright (c) 2024 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import sherlock  # type: ignore


class ClusterLock(sherlock.KubernetesLock):
    """
    A cluster lock that is used to lock the cluster for any operations
    across all of the conductor nodes.
    """

    # NOTE(rlin): The default TTL was 60s, which is too short for several
    #             cluster operations whose Server-Side Apply against the
    #             Cluster resource (and the surrounding logic) can easily
    #             exceed a minute on busy management clusters. When the
    #             lease expires mid-operation, sherlock loses its
    #             exclusivity guarantee and concurrent conductors can
    #             interleave reads/writes on the same Cluster object,
    #             producing stale-read races on the topology
    #             (e.g. parallel delete_nodegroup losing one of the
    #             topology removals). Bump the default to 5 minutes; the
    #             value remains overridable per-call via the `expire`
    #             kwarg for callers that know they need a tighter or
    #             looser bound.
    DEFAULT_EXPIRE: int = 300

    def __init__(self, cluster_id: str, expire: int = DEFAULT_EXPIRE):
        sherlock.configure(
            backend=sherlock.backends.KUBERNETES,
            retry_interval=1,
        )

        super().__init__(
            lock_name="cluster-%s" % cluster_id,
            k8s_namespace="magnum-system",
            expire=expire,
        )
