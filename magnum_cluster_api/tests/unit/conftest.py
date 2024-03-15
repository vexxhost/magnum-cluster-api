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
from magnum.common import context as magnum_context

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
def mock_pykube(session_mocker):
    session_mocker.patch("pykube.KubeConfig")
    session_mocker.patch("pykube.HTTPClient")


@pytest.fixture(scope="session")
def mock_cluster_lock(session_mocker):
    session_mocker.patch("kubernetes.config.load_config")
    session_mocker.patch("magnum_cluster_api.sync.ClusterLock.acquire")
    session_mocker.patch("magnum_cluster_api.sync.ClusterLock.release")


@pytest.fixture(scope="session")
def mock_validate_nodegroup(session_mocker):
    session_mocker.patch("magnum_cluster_api.utils.validate_nodegroup")


@pytest.fixture()
def ubuntu_driver(mock_cluster_lock, mock_pykube):
    yield driver.UbuntuDriver()
