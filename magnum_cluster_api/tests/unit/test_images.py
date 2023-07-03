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
from oslo_config import cfg

from magnum_cluster_api import images


@pytest.mark.parametrize(
    "version,image,image_repository",
    [
        ("v1.22.0", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.22.3", None),
        ("v1.22.17", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.22.3", None),
        ("v1.23.0", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.23.1", None),
        ("v1.23.17", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.23.1", None),
        ("v1.24.0", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.24.2", None),
        ("v1.24.17", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.24.2", None),
        ("v1.25.0", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.25.2", None),
        ("v1.25.17", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.25.2", None),
        ("v1.26.0", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.26.3", None),
        ("v1.26.3", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.26.3", None),
        ("v1.27.0", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.27.2", None),
        ("v1.27.3", "registry.k8s.io/autoscaling/cluster-autoscaler:v1.27.2", None),
        ("v1.22.0", "quay.io/vexxhost/cluster-autoscaler:v1.22.3", "quay.io/vexxhost"),
        ("v1.22.17", "quay.io/vexxhost/cluster-autoscaler:v1.22.3", "quay.io/vexxhost"),
        ("v1.23.0", "quay.io/vexxhost/cluster-autoscaler:v1.23.1", "quay.io/vexxhost"),
        ("v1.23.17", "quay.io/vexxhost/cluster-autoscaler:v1.23.1", "quay.io/vexxhost"),
        ("v1.24.0", "quay.io/vexxhost/cluster-autoscaler:v1.24.2", "quay.io/vexxhost"),
        ("v1.24.17", "quay.io/vexxhost/cluster-autoscaler:v1.24.2", "quay.io/vexxhost"),
        ("v1.25.0", "quay.io/vexxhost/cluster-autoscaler:v1.25.2", "quay.io/vexxhost"),
        ("v1.25.17", "quay.io/vexxhost/cluster-autoscaler:v1.25.2", "quay.io/vexxhost"),
        ("v1.26.0", "quay.io/vexxhost/cluster-autoscaler:v1.26.3", "quay.io/vexxhost"),
        ("v1.26.3", "quay.io/vexxhost/cluster-autoscaler:v1.26.3", "quay.io/vexxhost"),
        ("v1.27.0", "quay.io/vexxhost/cluster-autoscaler:v1.27.2", "quay.io/vexxhost"),
        ("v1.27.3", "quay.io/vexxhost/cluster-autoscaler:v1.27.2", "quay.io/vexxhost"),
    ],
)
def test_get_cluster_autoscaler_image(image_repository, version, image):
    if image_repository:
        cfg.CONF.set_override(
            "image_repository", image_repository, group="auto_scaling"
        )
    assert images.get_cluster_autoscaler_image(version) == image
