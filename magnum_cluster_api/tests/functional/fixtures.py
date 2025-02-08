# Copyright (c) 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0


import fixtures  # type: ignore

from magnum_cluster_api import resources


class ClusterClassFixture(fixtures.Fixture):
    def __init__(self, api, namespace, mutate_callback=None):
        super(ClusterClassFixture, self).__init__()
        self.api = api
        self.namespace = namespace
        self.mutate_callback = mutate_callback

    def _setUp(self):
        self.cluster_class = resources.ClusterClass(
            self.api, namespace=self.namespace.name
        )

        original_get_object = self.cluster_class.get_object

        def get_object_override():
            resource = original_get_object()
            if self.mutate_callback:
                self.mutate_callback(resource)
            return resource

        self.cluster_class.get_object = get_object_override
        self.cluster_class.apply()


class ClusterFixture(fixtures.Fixture):
    def __init__(self, context, api, namespace, magnum_cluster, mutate_callback=None):
        super(ClusterFixture, self).__init__()
        self.context = context
        self.api = api
        self.namespace = namespace
        self.magnum_cluster = magnum_cluster
        self.mutate_callback = mutate_callback

    def _setUp(self):
        self.cluster = resources.Cluster(
            self.context, self.api, self.magnum_cluster, namespace=self.namespace.name
        )

        original_get_object = self.cluster.get_object

        def get_object_override():
            resource = original_get_object()
            if self.mutate_callback:
                self.mutate_callback(resource)
            return resource

        self.cluster.get_object = get_object_override
        self.cluster.apply()
