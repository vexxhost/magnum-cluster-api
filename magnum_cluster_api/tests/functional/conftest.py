# Copyright (c) 2023 VEXXHOST, Inc.
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

import pytest

from magnum_cluster_api import objects


@pytest.fixture
def cluster(
    context,
    cluster_obj,
    ubuntu_driver,
    mock_validate_cluster,
    mock_osc,
    mock_certificates,
):
    try:
        ubuntu_driver.create_cluster(context, cluster_obj, 60)

        cluster_resource = objects.Cluster.for_magnum_cluster(
            ubuntu_driver.k8s_api, cluster_obj
        )
        cluster_resource.wait_for_observed_generation_changed(
            existing_observed_generation=1
        )

        cluster_obj.save.assert_called_once()
        cluster_obj.save.reset_mock()

        yield cluster_obj
    finally:
        ubuntu_driver.delete_cluster(context, cluster_obj)
