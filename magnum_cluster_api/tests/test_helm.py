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
import yaml
from oslo_concurrency import processutils

from magnum_cluster_api import helm


def test_helm_upgrade(mocker):
    namespace = "test-namespace"
    release_name = "test-release"
    chart_ref = "test-chart"
    values = {"test": "value"}

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    upgrade = helm.UpgradeReleaseCommand(
        namespace,
        release_name,
        chart_ref,
        values,
    )
    upgrade()

    mock_execute.assert_called_once_with(
        "helm",
        "upgrade",
        "--namespace",
        namespace,
        release_name,
        chart_ref,
        "--install",
        "--wait",
        "--values",
        "-",
        process_input=yaml.dump(values),
    )


def test_helm_delete(mocker):
    namespace = "test-namespace"
    release_name = "test-release"

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    delete = helm.DeleteReleaseCommand(namespace, release_name)
    delete()

    mock_execute.assert_called_once_with(
        "helm",
        "delete",
        "--namespace",
        namespace,
        release_name,
    )


def test_helm_delete_with_no_release(mocker):
    namespace = "test-namespace"
    release_name = "test-release"

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    mock_execute.side_effect = processutils.ProcessExecutionError(
        stderr=f"Error: uninstall: Release not loaded: {release_name}: release: not found"
    )

    delete = helm.DeleteReleaseCommand(namespace, release_name)

    with pytest.raises(processutils.ProcessExecutionError):
        delete()

    mock_execute.assert_called_once_with(
        "helm",
        "delete",
        "--namespace",
        namespace,
        release_name,
    )


def test_helm_delete_skip_missing_and_existing_release(mocker):
    namespace = "test-namespace"
    release_name = "test-release"

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    delete = helm.DeleteReleaseCommand(namespace, release_name, skip_missing=True)
    delete()

    mock_execute.assert_called_once_with(
        "helm",
        "delete",
        "--namespace",
        namespace,
        release_name,
    )


def test_helm_delete_with_skip_missing_and_no_release(mocker):
    namespace = "test-namespace"
    release_name = "test-release"

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    mock_execute.side_effect = processutils.ProcessExecutionError(
        stderr=f"Error: uninstall: Release not loaded: {release_name}: release: not found"
    )

    delete = helm.DeleteReleaseCommand(namespace, release_name, skip_missing=True)
    delete()

    mock_execute.assert_called_once_with(
        "helm",
        "delete",
        "--namespace",
        namespace,
        release_name,
    )
