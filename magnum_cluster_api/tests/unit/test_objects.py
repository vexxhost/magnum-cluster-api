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

import configparser
import textwrap

import pytest
from oslo_serialization import base64

from magnum_cluster_api import exceptions, objects


@pytest.fixture
def mock_openstack_cluster(mocker):
    mock_api = mocker.Mock()
    mocker.patch.object(
        objects.OpenStackCluster,
        "identity_ref_secret",
        new_callable=mocker.PropertyMock,
        return_value=mocker.Mock(
            obj={
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": "test-identity",
                    "namespace": "test-namespace",
                },
                "data": {
                    "clouds.yaml": base64.encode_as_text(
                        textwrap.dedent(
                            """
                                clouds:
                                  default:
                                    region_name: RegionOne
                                    verify: false
                                    auth:
                                      auth_url: https://example.com:5000/v3
                                      application_credential_id: cluster-api
                                      application_credential_secret: secret123
                                """
                        )
                    )
                },
            }
        ),
    )

    return objects.OpenStackCluster(
        mock_api,
        {
            "apiVersion": objects.OpenStackCluster.version,
            "kind": objects.OpenStackCluster.kind,
            "metadata": {
                "name": "test-cluster",
                "namespace": "test-namespace",
            },
            "spec": {
                "identityRef": {
                    "name": "test-identity",
                }
            },
            "status": {
                "externalNetwork": {
                    "id": "foo",
                },
                "network": {
                    "id": "bar",
                    "subnet": {
                        "id": "baz",
                    },
                },
            },
        },
    )


class TestOpenStackCluster:
    def test_floating_network_id(self, mock_openstack_cluster):
        assert (
            mock_openstack_cluster.floating_network_id
            == mock_openstack_cluster.obj["status"]["externalNetwork"]["id"]
        )

    def test_floating_network_id_not_ready(self, mock_openstack_cluster):
        del mock_openstack_cluster.obj["status"]["externalNetwork"]
        with pytest.raises(exceptions.OpenStackClusterExternalNetworkNotReady):
            mock_openstack_cluster.floating_network_id

    def test_network_id(self, mock_openstack_cluster):
        assert (
            mock_openstack_cluster.network_id
            == mock_openstack_cluster.obj["status"]["network"]["id"]
        )

    def test_network_id_not_ready(self, mock_openstack_cluster):
        del mock_openstack_cluster.obj["status"]["network"]["id"]
        with pytest.raises(exceptions.OpenStackClusterNetworkNotReady):
            mock_openstack_cluster.network_id

    def test_subnet_id(self, mock_openstack_cluster):
        assert (
            mock_openstack_cluster.subnet_id
            == mock_openstack_cluster.obj["status"]["network"]["subnet"]["id"]
        )

    def test_subnet_id_not_ready(self, mock_openstack_cluster):
        del mock_openstack_cluster.obj["status"]["network"]["subnet"]["id"]
        with pytest.raises(exceptions.OpenStackClusterSubnetNotReady):
            mock_openstack_cluster.subnet_id

    def test_cloud_controller_manager_config(self, mock_openstack_cluster):
        config = configparser.ConfigParser()
        config.read_string(mock_openstack_cluster.cloud_controller_manager_config)

        assert {s: dict(config.items(s)) for s in config.sections()} == {
            "Global": {
                "auth-url": mock_openstack_cluster.cloud_config["auth"]["auth_url"],
                "region": mock_openstack_cluster.cloud_config["region_name"],
                "application-credential-id": mock_openstack_cluster.cloud_config[
                    "auth"
                ]["application_credential_id"],
                "application-credential-secret": mock_openstack_cluster.cloud_config[
                    "auth"
                ]["application_credential_secret"],
                "tls-insecure": (
                    "false" if mock_openstack_cluster.cloud_config["verify"] else "true"
                ),
            },
            "LoadBalancer": {
                "floating-network-id": mock_openstack_cluster.floating_network_id,
                "network-id": mock_openstack_cluster.network_id,
                "subnet-id": mock_openstack_cluster.subnet_id,
            },
        }
