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

import openstack
import pytest
import shortuuid
from magnum.objects import fields
from tenacity import TryAgain, retry, stop_after_delay, wait_fixed

openstack.enable_logging(debug=True)


@pytest.fixture(scope="session")
def kube_tag():
    return os.getenv("KUBE_TAG", "v1.25.3")


@pytest.fixture(scope="session")
def conn():
    return openstack.connect(cloud="envvars")


@pytest.fixture(scope="session")
def image(conn, kube_tag):
    image_name = os.getenv("CAPI_IMAGE_NAME", f"ubuntu-2204-kube-{kube_tag}")
    return conn.image.find_image(image_name)


@pytest.fixture(scope="session")
def cluster_template(conn, image, kube_tag):
    cluster_template = conn.container_infra.create_cluster_template(
        name="k8s-%s" % shortuuid.uuid(),
        image_id=image.id,
        external_network_id="public",
        dns_nameserver="8.8.8.8",
        master_lb_enabled=True,
        master_flavor_id="m1.medium",
        flavor_id="m1.medium",
        network_driver="calico",
        docker_storage_driver="overlay2",
        coe="kubernetes",
        labels={
            "kube_tag": kube_tag,
            # NOTE(mnaser): GitHub actions uses 10.0.0.0/22 for it's network
            #               and we need to make sure we don't overlap with it.
            "fixed_subnet_cidr": "192.168.24.0/24",
        },
    )

    yield cluster_template

    conn.container_infra.delete_cluster_template(cluster_template)


@pytest.fixture()
def cluster(conn, cluster_template):
    def is_none_p(value):
        return value is None

    @retry(
        stop=stop_after_delay(600),
        wait=wait_fixed(1),
    )
    def wait_for_cluster_status(cluster, target_cluster_status):
        try:
            cluster = conn.container_infra.get_cluster(cluster.id)
        except openstack.exceptions.ResourceNotFound:
            if target_cluster_status == fields.ClusterStatus.DELETE_COMPLETE:
                return
            raise TryAgain()

        if "FAILED" in cluster.status:
            raise Exception(cluster.status_reason)
        if target_cluster_status == cluster.status:
            return cluster

        raise TryAgain()

    cluster = conn.container_infra.create_cluster(
        name="k8s-%s" % shortuuid.uuid(),
        cluster_template_id=cluster_template.id,
        master_count=1,
        node_count=1,
    )
    wait_for_cluster_status(cluster, fields.ClusterStatus.CREATE_COMPLETE)
    cluster = conn.container_infra.get_cluster(cluster.id)

    yield cluster

    conn.container_infra.delete_cluster(cluster.id)
    wait_for_cluster_status(cluster, fields.ClusterStatus.DELETE_COMPLETE)
