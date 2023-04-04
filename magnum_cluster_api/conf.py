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

from oslo_config import cfg

auto_scaling_opts = [
    cfg.StrOpt(
        "image_repository",
        default="registry.k8s.io/autoscaling",
        help="Image repository for the cluster auto-scaler.",
    ),
    cfg.StrOpt(
        "v1_22_image",
        default="$image_repository/cluster-autoscaler:v1.22.1",
        help="Image for the cluster auto-scaler for Kubernetes v1.22.",
    ),
    cfg.StrOpt(
        "v1_23_image",
        default="$image_repository/cluster-autoscaler:v1.23.0",
        help="Image for the cluster auto-scaler for Kubernetes v1.23.",
    ),
    cfg.StrOpt(
        "v1_24_image",
        default="$image_repository/cluster-autoscaler:v1.24.1",
        help="Image for the cluster auto-scaler for Kubernetes v1.24.",
    ),
    cfg.StrOpt(
        "v1_25_image",
        default="$image_repository/cluster-autoscaler:v1.25.1",
        help="Image for the cluster auto-scaler for Kubernetes v1.25.",
    ),
    cfg.StrOpt(
        "v1_26_image",
        default="$image_repository/cluster-autoscaler:v1.26.1",
        help="Image for the cluster auto-scaler for Kubernetes v1.26.",
    ),
]

CONF = cfg.CONF
CONF.register_opts(auto_scaling_opts, "auto_scaling")
