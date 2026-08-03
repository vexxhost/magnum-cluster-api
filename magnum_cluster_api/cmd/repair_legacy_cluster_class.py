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

import click

from magnum_cluster_api import magnum_cluster_api


@click.command()
@click.argument("cluster_class_name")
@click.option("--namespace", default="magnum-system", show_default=True)
@click.option(
    "--yes",
    is_flag=True,
    help="Apply the repair without an interactive confirmation.",
)
def main(cluster_class_name: str, namespace: str, yes: bool) -> None:
    """Repair proxy file patches in one legacy CLUSTER_CLASS_NAME."""
    if not yes:
        click.confirm(
            "This changes the bootstrap configuration for every Cluster using "
            f"{cluster_class_name} and may trigger Machine rollouts. Continue?",
            abort=True,
        )

    result = magnum_cluster_api.Driver(namespace).repair_legacy_cluster_class(
        cluster_class_name
    )
    if result == magnum_cluster_api.LegacyClusterClassRepairResult.Repaired:
        click.echo(f"Repaired ClusterClass {namespace}/{cluster_class_name}.")
    elif result == magnum_cluster_api.LegacyClusterClassRepairResult.AlreadyFixed:
        click.echo(
            f"ClusterClass {namespace}/{cluster_class_name} is already repaired."
        )
    elif result == magnum_cluster_api.LegacyClusterClassRepairResult.OutOfScope:
        click.echo(
            f"ClusterClass {namespace}/{cluster_class_name} is outside the supported "
            "legacy repair scope."
        )
    else:
        raise click.ClickException(f"Unexpected repair result: {result!r}")
