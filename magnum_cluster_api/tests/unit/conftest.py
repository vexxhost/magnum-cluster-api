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
