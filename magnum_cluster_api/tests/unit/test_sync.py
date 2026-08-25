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

from unittest import TestCase, mock

from kubernetes.config.config_exception import ConfigException
from oslo_utils import uuidutils

from magnum_cluster_api.sync import ClusterLock, _load_kubernetes_client


class ClusterLockTestCase(TestCase):
    @mock.patch("magnum_cluster_api.sync._load_kubernetes_client")
    def test_cluster_lock_init_with_no_expire(self, mock_load_kubernetes_client):
        cluster_id = uuidutils.generate_uuid()

        lock = ClusterLock(cluster_id)

        self.assertEqual(lock.lock_name, "cluster-%s" % cluster_id)
        self.assertEqual(lock.k8s_namespace, "magnum-system")
        self.assertEqual(lock.expire, ClusterLock.DEFAULT_EXPIRE)
        self.assertIs(lock.client, mock_load_kubernetes_client.return_value)

    @mock.patch("magnum_cluster_api.sync._load_kubernetes_client")
    def test_cluster_lock_init_with_expire(self, mock_load_kubernetes_client):
        cluster_id = uuidutils.generate_uuid()
        expire = 60

        lock = ClusterLock(cluster_id, expire)

        self.assertEqual(lock.lock_name, "cluster-%s" % cluster_id)
        self.assertEqual(lock.k8s_namespace, "magnum-system")
        self.assertEqual(lock.expire, expire)
        self.assertIs(lock.client, mock_load_kubernetes_client.return_value)

    @mock.patch("magnum_cluster_api.sync.kubernetes_client.CoordinationV1Api")
    @mock.patch("magnum_cluster_api.sync.kubernetes_config.load_config")
    @mock.patch("magnum_cluster_api.sync.kubernetes_config.load_incluster_config")
    def test_load_kubernetes_client_uses_incluster_config(
        self,
        mock_load_incluster_config,
        mock_load_config,
        mock_coordination_v1_api,
    ):
        client = _load_kubernetes_client()

        mock_load_incluster_config.assert_called_once_with()
        mock_load_config.assert_not_called()
        mock_coordination_v1_api.assert_called_once_with()
        self.assertIs(client, mock_coordination_v1_api.return_value)

    @mock.patch("magnum_cluster_api.sync.kubernetes_client.CoordinationV1Api")
    @mock.patch("magnum_cluster_api.sync.kubernetes_config.load_config")
    @mock.patch("magnum_cluster_api.sync.kubernetes_config.load_incluster_config")
    def test_load_kubernetes_client_falls_back_to_kubeconfig(
        self,
        mock_load_incluster_config,
        mock_load_config,
        mock_coordination_v1_api,
    ):
        mock_load_incluster_config.side_effect = ConfigException("not in a pod")

        client = _load_kubernetes_client()

        mock_load_incluster_config.assert_called_once_with()
        mock_load_config.assert_called_once_with()
        mock_coordination_v1_api.assert_called_once_with()
        self.assertIs(client, mock_coordination_v1_api.return_value)
