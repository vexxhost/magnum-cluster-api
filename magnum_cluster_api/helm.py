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

import yaml
from oslo_concurrency import processutils

from magnum_cluster_api import exceptions


class Command:
    def __init__(self, kubeconfig):
        self.kubeconfig = kubeconfig

    def __call__(self, *args, **kwargs):
        if self.kubeconfig:
            kwargs["env_variables"] = os.environ.copy()
            kwargs["env_variables"]["KUBECONFIG"] = self.kubeconfig
        try:
            return processutils.execute("helm", *self.COMMAND, *args, **kwargs)
        except processutils.ProcessExecutionError as e:
            if "Kubernetes cluster unreachable" in e.stderr:
                raise exceptions.ClusterNotReady()
            else:
                raise


class VersionCommand(Command):
    COMMAND = ["version"]


class ReleaseCommand(Command):
    def __init__(self, namespace, release_name, kubeconfig=None):
        super().__init__(kubeconfig)
        self.namespace = namespace
        self.release_name = release_name

    def __call__(self, *args, **kwargs):
        return super().__call__(
            "--namespace",
            self.namespace,
            self.release_name,
            *args,
            **kwargs,
        )


class GetValuesReleaseCommand(ReleaseCommand):
    COMMAND = ["get", "values"]

    def __call__(self):
        try:
            stdout, _ = super().__call__(
                "--output",
                "yaml",
            )
        except processutils.ProcessExecutionError as e:
            if "release: not found" in e.stderr:
                raise exceptions.HelmReleaseNotFound(self.release_name)
            else:
                raise

        return yaml.safe_load(stdout)


class UpgradeReleaseCommand(ReleaseCommand):
    COMMAND = ["upgrade"]

    def __init__(self, namespace, release_name, chart_ref, values={}, kubeconfig=None):
        super().__init__(namespace, release_name, kubeconfig=kubeconfig)
        self.chart_ref = chart_ref
        self.values = values

    def __call__(self):
        return super().__call__(
            self.chart_ref,
            "--install",
            "--values",
            "-",
            process_input=yaml.dump(self.values),
        )


class DeleteReleaseCommand(ReleaseCommand):
    COMMAND = ["delete"]

    def __init__(self, namespace, release_name, skip_missing=False):
        super().__init__(namespace, release_name)
        self.skip_missing = skip_missing

    def __call__(self):
        try:
            return super().__call__()
        except processutils.ProcessExecutionError as e:
            if "release: not found" in e.stderr:
                if self.skip_missing:
                    pass
                else:
                    raise exceptions.HelmReleaseNotFound(self.release_name)
            else:
                raise
