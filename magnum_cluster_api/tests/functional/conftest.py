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

import os
from datetime import datetime, timedelta
from unittest import mock

import openstack
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from magnum.objects import fields
from oslo_utils import uuidutils  # type: ignore

from magnum_cluster_api import objects


@pytest.fixture(scope="session")
def image():
    return {
        "id": uuidutils.generate_uuid(),
        "os_distro": "ubuntu",
    }


@pytest.fixture(scope="session")
def kube_tag():
    return os.getenv("KUBE_TAG", "v1.25.3")


@pytest.fixture()
def cluster_template(mocker, kube_tag, image):
    cluster_template = mocker.MagicMock()

    cluster_template.image_id = image["id"]

    cluster_template.master_lb_enabled = True
    cluster_template.external_network_id = uuidutils.generate_uuid()
    cluster_template.dns_nameserver = "8.8.8.8"

    cluster_template.master_flavor_id = uuidutils.generate_uuid()
    cluster_template.flavor_id = uuidutils.generate_uuid()

    cluster_template.labels = {
        "kube_tag": kube_tag,
    }

    return cluster_template


@pytest.fixture()
def node_group_obj(mocker, cluster_template):
    node_group = mocker.MagicMock()
    node_group.name = "default-worker"
    node_group.role = "worker"
    node_group.node_count = 1
    node_group.flavor_id = cluster_template.flavor_id
    node_group.image_id = cluster_template.image_id
    node_group.labels = {}
    node_group.status = fields.ClusterStatus.CREATE_IN_PROGRESS

    return node_group


@pytest.fixture()
def cluster_obj(mocker, cluster_template, node_group_obj):
    cluster = mocker.MagicMock()
    cluster.project_id = uuidutils.generate_uuid()
    cluster.uuid = uuidutils.generate_uuid()
    cluster.fixed_network = None
    cluster.fixed_subnet = None
    cluster.keypair = None
    cluster.labels = {}

    cluster.cluster_template = cluster_template
    cluster.master_lb_enabled = cluster_template.master_lb_enabled
    cluster.master_flavor_id = cluster_template.master_flavor_id
    cluster.flavor_id = cluster_template.flavor_id

    cluster.master_count = 1

    cluster.default_ng_master.image_id = cluster_template.image_id
    cluster.nodegroups = [node_group_obj]

    return cluster


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

        cluster_resource = objects.Cluster.for_magnum_cluster(ubuntu_driver.k8s_api, cluster_obj)
        cluster_resource.wait_for_observed_generation_changed(existing_observed_generation=1)

        yield cluster_obj
    finally:
        ubuntu_driver.delete_cluster(context, cluster_obj)
