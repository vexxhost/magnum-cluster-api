# Copyright (c) 2026 VEXXHOST, Inc.
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

import types

from magnum_cluster_api.integrations import cinder


def test_get_default_boot_volume_type_uses_cinder_helper(context, mocker):
    cinder_client = mocker.Mock()
    default_volume_type = types.SimpleNamespace(name="rbd-fast")
    openstack_api = mocker.patch(
        "magnum_cluster_api.integrations.cinder.clients.get_openstack_api"
    )
    openstack_api.return_value.cinder.return_value = cinder_client
    get_default_volume_type = mocker.patch(
        "magnum_cluster_api.integrations.cinder.utils.get_default_volume_type",
        return_value=default_volume_type,
    )
    mocker.patch(
        "magnum_cluster_api.integrations.cinder.CONF.cinder.default_boot_volume_type",
        None,
    )

    assert cinder.get_default_boot_volume_type(context) == "rbd-fast"
    get_default_volume_type.assert_called_once_with(cinder_client)
