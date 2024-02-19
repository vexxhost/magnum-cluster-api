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

import itertools

import yaml
from oslo_concurrency import processutils
from oslo_log import log as logging

from magnum_cluster_api import exceptions, image_utils

LOG = logging.getLogger(__name__)


class Command:
    def __call__(self, *args, **kwargs):
        return processutils.execute("helm", *self.COMMAND, *args, **kwargs)


class VersionCommand(Command):
    COMMAND = ["version"]


class ReleaseCommand(Command):
    def __init__(self, namespace, release_name):
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
            return super().__call__(
                "--output",
                "yaml",
            )
        except processutils.ProcessExecutionError as e:
            if "release: not found" in e.stderr:
                raise exceptions.HelmReleaseNotFound(self.release_name)
            else:
                raise


class UpgradeReleaseCommand(ReleaseCommand):
    COMMAND = ["upgrade"]

    def __init__(self, namespace, release_name, chart_ref, values={}):
        super().__init__(namespace, release_name)
        self.chart_ref = chart_ref
        self.values = values

    def __call__(self):
        try:
            return super().__call__(
                self.chart_ref,
                "--install",
                "--values",
                "-",
                process_input=yaml.dump(self.values),
            )
        except processutils.ProcessExecutionError as e:
            if "UPGRADE FAILED: another operation" in e.stderr:
                LOG.info("Helm release %s is already in progress", self.release_name)
            elif "UPGRADE FAILED: release: already exists" in e.stderr:
                LOG.info("Helm release %s already exists", self.release_name)
            else:
                raise


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


class TemplateReleaseCommand(ReleaseCommand):
    COMMAND = ["template"]

    def __init__(self, namespace, release_name, chart_ref, values={}):
        super().__init__(namespace, release_name)
        self.chart_ref = chart_ref
        self.values = values

    def __call__(self, repository=None, replacements=[]):
        try:
            docs = []
            data, _ = super().__call__(
                self.chart_ref,
                "--values",
                "-",
                process_input=yaml.dump(self.values),
            )

            # NOTE(oleks): ClusterResourceSet fails to be applied without namespace set in resources.
            #              On the other hand, helm template doesn't output namespace. We set it manually
            #              until  https://github.com/helm/helm/issues/10737 is fixed.
            for doc in yaml.safe_load_all(data):
                if doc["kind"] in ("DaemonSet", "Deployment", "StatefulSet"):
                    for container in itertools.chain(
                        doc["spec"]["template"]["spec"].get("initContainers", []),
                        doc["spec"]["template"]["spec"]["containers"],
                    ):
                        for src, dst in replacements:
                            container["image"] = container["image"].replace(src, dst)
                        if repository:
                            container["image"] = image_utils.get_image(
                                container["image"], repository
                            )

                if doc["kind"] not in ("ClusterRole", "ClusterRoleBinding"):
                    doc["metadata"]["namespace"] = self.namespace
                docs.append(doc)
            return yaml.safe_dump_all(docs, default_flow_style=False)

        except processutils.ProcessExecutionError:
            LOG.info("Helm template %s failed", self.release_name)
            raise
