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

from click.testing import CliRunner

from magnum_cluster_api.cmd import repair_legacy_cluster_class


def test_repairs_one_cluster_class(mocker):
    driver = mocker.patch(
        "magnum_cluster_api.cmd.repair_legacy_cluster_class."
        "magnum_cluster_api.Driver"
    ).return_value
    driver.repair_legacy_cluster_class.return_value = True

    result = CliRunner().invoke(
        repair_legacy_cluster_class.main,
        ["--yes", "--namespace", "test-system", "magnum-v0.34.2"],
    )

    assert result.exit_code == 0
    driver.repair_legacy_cluster_class.assert_called_once_with("magnum-v0.34.2")
    assert "Repaired ClusterClass test-system/magnum-v0.34.2." in result.output


def test_warns_before_repair(mocker):
    driver = mocker.patch(
        "magnum_cluster_api.cmd.repair_legacy_cluster_class."
        "magnum_cluster_api.Driver"
    )

    result = CliRunner().invoke(
        repair_legacy_cluster_class.main,
        ["magnum-v0.34.2"],
        input="n\n",
    )

    assert result.exit_code == 1
    assert "may trigger Machine rollouts" in result.output
    driver.assert_not_called()
