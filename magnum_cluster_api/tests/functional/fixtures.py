# Copyright (c) 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0


import fixtures
import pykube  # type: ignore

from magnum_cluster_api import magnum_cluster_api, resources


class ClusterClassFixture(fixtures.Fixture):
    def __init__(self, api, namespace: str, mutate_callback=None):
        super(ClusterClassFixture, self).__init__()
        self.api = api
        self.namespace = namespace
        self.mutate_callback = mutate_callback

    def _setUp(self):
        self.cluster_class = resources.ClusterClass(self.api, namespace=self.namespace)

        original_get_resource = self.cluster_class.get_resource

        def get_resource_override():
            resource = original_get_resource()
            if self.mutate_callback:
                self.mutate_callback(resource)
            return resource

        self.cluster_class.get_resource = get_resource_override
        self.cluster_class.apply()


class ClusterFixture(fixtures.Fixture):
    def __init__(
        self,
        context,
        api: magnum_cluster_api.KubeClient,
        pykube_api: pykube.HTTPClient,
        namespace: str,
        magnum_cluster,
        mutate_callback=None,
    ):
        super(ClusterFixture, self).__init__()
        self.context = context
        self.api = api
        self.pykube_api = pykube_api
        self.namespace = namespace
        self.magnum_cluster = magnum_cluster
        self.mutate_callback = mutate_callback

    def _setUp(self):
        self.cluster = resources.Cluster(
            self.context,
            self.api,
            self.pykube_api,
            self.magnum_cluster,
            namespace=self.namespace,
        )

        original_get_resource = self.cluster.get_resource

        def get_resource_override():
            resource = original_get_resource()
            if self.mutate_callback:
                self.mutate_callback(resource)
            return resource

        magnum_cluster_api.MagnumCluster(
            self.magnum_cluster, resources.CLUSTER_CLASS_NAME, namespace=self.namespace
        ).apply_cluster_class()

        self.cluster.get_resource = get_resource_override
        self.cluster.apply()
