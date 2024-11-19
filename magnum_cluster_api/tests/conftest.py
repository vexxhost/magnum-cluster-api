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

import os
from datetime import datetime, timedelta
from unittest import mock

import openstack
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from magnum.common import context as magnum_context  # type: ignore
from magnum.objects import fields
from magnum.tests.unit.objects import utils
from oslo_utils import uuidutils  # type: ignore
from responses import matchers

from magnum_cluster_api import driver


@pytest.fixture
def context():
    return magnum_context.RequestContext(
        auth_token_info={
            "token": {"project": {"id": "fake_project"}, "user": {"id": "fake_user"}}
        },
        project_id="fake_project",
        user_id="fake_user",
        is_admin=False,
    )


@pytest.fixture(scope="session")
def mock_cluster_lock(session_mocker):
    session_mocker.patch("kubernetes.config.load_config")
    session_mocker.patch("magnum_cluster_api.sync.ClusterLock.acquire")
    session_mocker.patch("magnum_cluster_api.sync.ClusterLock.release")


@pytest.fixture(scope="session")
def mock_validate_cluster(session_mocker):
    session_mocker.patch("magnum_cluster_api.utils.validate_cluster")


@pytest.fixture(scope="session")
def mock_validate_nodegroup(session_mocker):
    session_mocker.patch("magnum_cluster_api.utils.validate_nodegroup")


@pytest.fixture()
def ubuntu_driver(mock_cluster_lock):
    yield driver.UbuntuDriver()


@pytest.fixture(scope="session")
def image():
    return {
        "id": uuidutils.generate_uuid(),
        "os_distro": "ubuntu",
    }


@pytest.fixture(scope="session")
def mock_osc(session_mocker, image):
    mock_clients = session_mocker.patch(
        "magnum_cluster_api.clients.OpenStackClients"
    ).return_value

    # NOTE(mnaser): Since there are reference in the Magnum code to the
    #               OpenStackClients, we need to make sure we mock it
    #               in the Magnum code as well.
    session_mocker.patch(
        "magnum.common.clients.OpenStackClients",
        return_value=mock_clients,
    )

    # Keystone
    mock_keystone_client = mock_clients.keystone.return_value.client
    mock_keystone_client.application_credentials.create.return_value = (
        openstack.identity.v3.application_credential.ApplicationCredential(
            id="fake_id", secret="fake_secret"
        )
    )

    # Glance
    mock_glance_client = mock_clients.glance.return_value
    mock_glance_client.images.get.return_value = image

    # Cinder
    mock_cinder_client = mock_clients.cinder.return_value
    mock_cinder_client.volume_types.default.return_value.name = "__DEFAULT__"
    mock_clients.cinder_region_name.return_value = "RegionOne"

    # Others
    mock_clients.url_for.return_value = "http://fake_url"

    return mock_clients


@pytest.fixture(scope="session")
def mock_get_server_group(session_mocker):
    mock_get_server_group = session_mocker.patch(
        "magnum_cluster_api.utils.get_server_group_id"
    )
    mock_get_server_group.return_value = uuidutils.generate_uuid()


@pytest.fixture(scope="session")
def mock_certificate() -> mock.MagicMock:
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    cert: x509.Certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "test")]))
        .issuer_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "test")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now())
        .not_valid_after(datetime.now() + timedelta(days=365))
        .sign(key, hashes.SHA256(), default_backend())
    )

    fake_certificate = mock.MagicMock()
    fake_certificate.get_certificate.return_value = cert.public_bytes(
        serialization.Encoding.PEM
    )
    fake_certificate.get_private_key_passphrase.return_value = "fake_passphrase"
    fake_certificate.get_private_key.return_value = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(
            fake_certificate.get_private_key_passphrase.return_value.encode("utf-8")
        ),
    )

    return fake_certificate


@pytest.fixture(scope="session")
def mock_get_cluster_ca_certificate(session_mocker, mock_certificate) -> mock.MagicMock:
    mock_get_cluster_ca_certificate = session_mocker.patch(
        "magnum.conductor.handlers.common.cert_manager.get_cluster_ca_certificate"
    )
    mock_get_cluster_ca_certificate.return_value = mock_certificate

    return mock_get_cluster_ca_certificate


@pytest.fixture(scope="session")
def mock_get_cluster_magnum_cert(session_mocker, mock_certificate) -> mock.MagicMock:
    mock_get_cluster_ca_certificate = session_mocker.patch(
        "magnum.conductor.handlers.common.cert_manager.get_cluster_magnum_cert"
    )
    mock_get_cluster_ca_certificate.return_value = mock_certificate

    return mock_get_cluster_ca_certificate


@pytest.fixture(scope="session")
def mock_certificates(mock_get_cluster_ca_certificate, mock_get_cluster_magnum_cert):
    pass


@pytest.fixture(scope="session")
def kube_tag():
    return os.getenv("KUBE_TAG", "v1.25.3")


@pytest.fixture()
def cluster_template(context, image, kube_tag):
    cluster_template = utils.get_test_cluster_template(
        context,
        image_id=image["id"],
        master_lb_enabled=True,
        external_network_id=uuidutils.generate_uuid(),
        dns_nameserver="8.8.8.8",
        master_flavor_id=uuidutils.generate_uuid(),
        flavor_id=uuidutils.generate_uuid(),
        cluster_distro="ubuntu",
        labels={"kube_tag": kube_tag},
    )
    cluster_template.save = mock.MagicMock()

    return cluster_template


@pytest.fixture()
def control_plane_node_group_obj(context, cluster_template):
    node_group = utils.get_test_nodegroup(
        context,
        name="default-master",
        role="master",
        node_count=1,
        flavor_id=cluster_template.master_flavor_id,
        image_id=cluster_template.image_id,
        labels=cluster_template.labels,
        status=fields.ClusterStatus.CREATE_IN_PROGRESS,
    )
    node_group.save = mock.MagicMock()

    yield node_group


@pytest.fixture()
def worker_node_group_obj(context, cluster_template):
    node_group = utils.get_test_nodegroup(
        context,
        name="default-worker",
        role="worker",
        node_count=1,
        flavor_id=cluster_template.master_flavor_id,
        image_id=cluster_template.image_id,
        labels=cluster_template.labels,
        status=fields.ClusterStatus.CREATE_IN_PROGRESS,
    )
    node_group.save = mock.MagicMock()

    yield node_group


@pytest.fixture()
def cluster_obj(
    mocker, cluster_template, control_plane_node_group_obj, worker_node_group_obj
):
    mocker.patch(
        "magnum.objects.NodeGroup.list",
        return_value=[control_plane_node_group_obj, worker_node_group_obj],
    )

    mocker.patch(
        "magnum.objects.ClusterTemplate.get_by_uuid",
        return_value=cluster_template,
    )

    cluster = utils.get_test_cluster(
        context,
        keypair="fake_keypair",
        master_flavor_id=cluster_template.master_flavor_id,
        flavor_id=cluster_template.flavor_id,
        image_id=cluster_template.image_id,
        ca_cert_ref=uuidutils.generate_uuid(),
        magnum_cert_ref=uuidutils.generate_uuid(),
        etcd_ca_cert_ref=uuidutils.generate_uuid(),
        front_proxy_ca_cert_ref=uuidutils.generate_uuid(),
        labels=cluster_template.labels,
    )
    cluster.save = mock.MagicMock()

    return cluster


@pytest.fixture
def server_side_apply_matcher():
    return matchers.query_param_matcher(
        {
            "fieldManager": "atmosphere-operator",
            "force": "True",
        }
    )
