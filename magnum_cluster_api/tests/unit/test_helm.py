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

from magnum_cluster_api import exceptions, helm


def test_helm_upgrade(mocker):
    namespace = "test-namespace"
    release_name = "test-release"
    chart_ref = "test-chart"
    values = {"test": "value"}

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    mock_execute.return_value = ("", "")
    upgrade = helm.UpgradeReleaseCommand(
        namespace,
        release_name,
        chart_ref,
        values,
    )
    upgrade()

    mock_execute.assert_has_calls(
        [
            mocker.call(
                "helm",
                "upgrade",
                "--namespace",
                namespace,
                release_name,
                chart_ref,
                "--install",
                "--values",
                "-",
                process_input=yaml.dump(values),
            ),
        ]
    )


def test_helm_upgrade_with_in_progress_operation(mocker):
    namespace = "test-namespace"
    release_name = "test-release"
    chart_ref = "test-chart"
    values = {"test": "value"}

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    mock_execute.side_effect = processutils.ProcessExecutionError(
        stderr="Error: UPGRADE FAILED: another operation (install/upgrade/rollback) is in progress"
    )
    upgrade = helm.UpgradeReleaseCommand(
        namespace,
        release_name,
        chart_ref,
        values,
    )
    upgrade()

    mock_execute.assert_has_calls(
        [
            mocker.call(
                "helm",
                "upgrade",
                "--namespace",
                namespace,
                release_name,
                chart_ref,
                "--install",
                "--values",
                "-",
                process_input=yaml.dump(values),
            ),
        ]
    )


def test_helm_upgrade_with_existing_release(mocker):
    namespace = "test-namespace"
    release_name = "test-release"
    chart_ref = "test-chart"
    values = {"test": "value"}

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    mock_execute.side_effect = processutils.ProcessExecutionError(
        stderr="Error: UPGRADE FAILED: release: already exists"
    )
    upgrade = helm.UpgradeReleaseCommand(
        namespace,
        release_name,
        chart_ref,
        values,
    )
    upgrade()

    mock_execute.assert_has_calls(
        [
            mocker.call(
                "helm",
                "upgrade",
                "--namespace",
                namespace,
                release_name,
                chart_ref,
                "--install",
                "--values",
                "-",
                process_input=yaml.dump(values),
            ),
        ]
    )


def test_helm_upgrade_with_unknown_error(mocker):
    namespace = "test-namespace"
    release_name = "test-release"
    chart_ref = "test-chart"
    values = {"test": "value"}

    mock_execute = mocker.patch("oslo_concurrency.processutils.execute")
    mock_execute.side_effect = processutils.ProcessExecutionError(
        stderr="Error: UPGRADE FAILED: test-release has no deployed releases"
    )
    upgrade = helm.UpgradeReleaseCommand(
        namespace,
        release_name,
        chart_ref,
        values,
    )

    with pytest.raises(processutils.ProcessExecutionError):
        upgrade()

    mock_execute.assert_has_calls(
        [
            mocker.call(
                "helm",
                "upgrade",
                "--namespace",
                namespace,
                release_name,
                chart_ref,
                "--install",
                "--values",
                "-",
                process_input=yaml.dump(values),
            ),
        ]
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

    with pytest.raises(exceptions.HelmReleaseNotFound):
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
