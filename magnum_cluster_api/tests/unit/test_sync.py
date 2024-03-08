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

from unittest import mock

from magnum.tests import base
from oslo_utils import uuidutils

from magnum_cluster_api.sync import ClusterLock


@mock.patch("kubernetes.config.load_config")
class ClusterLockTestCase(base.TestCase):
    def test_cluster_lock_init_with_no_expire(self, mock_load_config):
        cluster_id = uuidutils.generate_uuid()

        lock = ClusterLock(cluster_id)

        self.assertEqual(lock.lock_name, "cluster-%s" % cluster_id)
        self.assertEqual(lock.k8s_namespace, "magnum-system")
        self.assertEqual(lock.expire, ClusterLock.DEFAULT_EXPIRE)

    def test_cluster_lock_init_with_expire(self, mock_load_config):
        cluster_id = uuidutils.generate_uuid()
        expire = 60

        lock = ClusterLock(cluster_id, expire)

        self.assertEqual(lock.lock_name, "cluster-%s" % cluster_id)
        self.assertEqual(lock.k8s_namespace, "magnum-system")
        self.assertEqual(lock.expire, expire)
