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

import textwrap

import pykube  # type: ignore
import pytest
import responses
from novaclient.v2 import flavors  # type: ignore

from magnum_cluster_api import resources


@pytest.fixture(scope="session")
def kubeconfig(tmp_path_factory):
    kubeconfig = tmp_path_factory.mktemp("pykube") / "kubeconfig"
    kubeconfig.write_text(
        textwrap.dedent(
            """
            # TODO: Replace with a more realistic example
            current-context: thecluster
            clusters:
                - name: thecluster
                  cluster: {}
            users:
                - name: admin
                  user:
                    username: adm
                    password: somepassword
            contexts:
                - name: thecluster
                  context:
                    cluster: thecluster
                    user: admin
                - name: second
                  context: secondcontext
            """
        )
    )

    return pykube.KubeConfig.from_file(str(kubeconfig))


@pytest.fixture(scope="session")
def pykube_api(kubeconfig):
    return pykube.HTTPClient(kubeconfig)


@pytest.fixture(scope="session")
def requests_mock(session_mocker, kubeconfig):
    session_mocker.patch(
        "pykube.KubeConfig.from_env",
        return_value=kubeconfig,
    )

    return responses.RequestsMock(
        target="pykube.http.KubernetesHTTPAdapter._do_send",
    )


@pytest.fixture(scope="session")
def mock_rust_driver(session_mocker):
    return session_mocker.patch("magnum_cluster_api.magnum_cluster_api.Driver")


@pytest.fixture()
def cluster_topology_variable(
    context, mocker, cluster_obj, pykube_api, mock_osc, mock_get_server_group
):
    """Return a callable that builds a Cluster and walks a topology variable path.

    Usage::

        cluster_topology_variable("apiServerLoadBalancer")
        cluster_topology_variable("apiServerLoadBalancer", "provider",
                                  extra_labels={"octavia_provider": "ovn"})
    """
    mocker.patch(
        "magnum_cluster_api.resources.generate_machine_deployments_for_cluster",
        return_value=[],
    )
    mocker.patch(
        "magnum_cluster_api.utils.ensure_controlplane_server_group",
        return_value="sg-1",
    )
    mocker.patch(
        "magnum_cluster_api.utils.lookup_flavor",
        return_value=flavors.Flavor(
            None, {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1}
        ),
    )
    mocker.patch(
        "magnum_cluster_api.utils.lookup_image",
        return_value={"id": "img-1"},
    )

    original_labels = dict(cluster_obj.labels)

    def _get(*path, extra_labels=None):
        labels = dict(cluster_obj.labels)
        if extra_labels:
            labels.update(extra_labels)
        cluster_obj.labels = labels
        try:
            cluster_res = resources.Cluster(
                context, api=None, pykube_api=pykube_api, cluster=cluster_obj
            )
            obj = cluster_res.get_object()
        finally:
            cluster_obj.labels = dict(original_labels)
        variables = {
            v["name"]: v["value"] for v in obj["spec"]["topology"]["variables"]
        }
        result = variables
        for key in path:
            result = result[key]
        return result

    return _get
