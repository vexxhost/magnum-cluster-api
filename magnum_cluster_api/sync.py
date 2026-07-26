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
from kubernetes import client as kubernetes_client  # type: ignore
from kubernetes import config as kubernetes_config  # type: ignore
from kubernetes.config.config_exception import ConfigException  # type: ignore


def _load_kubernetes_client() -> kubernetes_client.CoordinationV1Api:
    try:
        kubernetes_config.load_incluster_config()
    except ConfigException:
        kubernetes_config.load_config()

    return kubernetes_client.CoordinationV1Api()


class ClusterLock(sherlock.KubernetesLock):
    """
    A cluster lock that is used to lock the cluster for any operations
    across all of the conductor nodes.
    """

    DEFAULT_EXPIRE: int = 60

    def __init__(self, cluster_id: str, expire: int = DEFAULT_EXPIRE):
        sherlock.configure(
            backend=sherlock.backends.KUBERNETES,
            retry_interval=1,
        )

        super().__init__(
            lock_name="cluster-%s" % cluster_id,
            k8s_namespace="magnum-system",
            expire=expire,
            client=_load_kubernetes_client(),
        )
