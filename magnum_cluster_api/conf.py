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

cloud_controller_manager_opts = [
    cfg.StrOpt(
        "legacy_image_repository",
        default="docker.io/k8scloudprovider",
        help="Legacy image repository for the OpenStack cloud controller manager.",
    ),
    cfg.StrOpt(
        "v1_22_image",
        default="$legacy_image_repository/openstack-cloud-controller-manager:v1.22.2",
        help="Image for the OpenStack cloud controller manager for Kubernetes v1.22.",
    ),
    cfg.StrOpt(
        "v1_23_image",
        default="$legacy_image_repository/openstack-cloud-controller-manager:v1.23.4",
        help="Image for the OpenStack cloud controller manager for Kubernetes v1.23.",
    ),
    cfg.StrOpt(
        "image_repository",
        default="registry.k8s.io/provider-os",
        help="Image repository for the OpenStack cloud controller manager.",
    ),
    cfg.StrOpt(
        "v1_24_image",
        default="$image_repository/openstack-cloud-controller-manager:v1.24.6",
        help="Image for the OpenStack cloud controller manager for Kubernetes v1.24.",
    ),
    cfg.StrOpt(
        "v1_25_image",
        default="$image_repository/openstack-cloud-controller-manager:v1.25.5",
        help="Image for the OpenStack cloud controller manager for Kubernetes v1.25.",
    ),
    cfg.StrOpt(
        "v1_26_image",
        default="$image_repository/openstack-cloud-controller-manager:v1.26.2",
        help="Image for the OpenStack cloud controller manager for Kubernetes v1.26.",
    ),
]

csi_opts = [
    cfg.StrOpt(
        "image_repository",
        default="registry.k8s.io/sig-storage",
        help="Image repository for the container storage interface.",
    ),
    cfg.StrOpt(
        "attacher_image",
        default="$image_repository/csi-attacher:v4.2.0",
        help="Image for the attacher.",
    ),
    cfg.StrOpt(
        "provisioner_image",
        default="$image_repository/csi-provisioner:v3.4.1",
        help="Image for the provisioner.",
    ),
    cfg.StrOpt(
        "snapshotter_image",
        default="$image_repository/csi-snapshotter:v6.2.1",
        help="Image for the snapshotter.",
    ),
    cfg.StrOpt(
        "resizer_image",
        default="$image_repository/csi-resizer:v1.7.0",
        help="Image for the resizer.",
    ),
    cfg.StrOpt(
        "liveness_probe_image",
        default="$image_repository/livenessprobe:v2.9.0",
        help="Image for the liveness probe.",
    ),
    cfg.StrOpt(
        "node_driver_registrar_image",
        default="$image_repository/csi-node-driver-registrar:v2.6.2",
        help="Image for the node driver registrar.",
    ),
    cfg.StrOpt(
        "plugin_image",
        default="$image_repository/cinder-csi-plugin:v1.3.0",
        help="Image for the Cinder CSI plugin.",
    ),
]

cinder_csi_opts = [
    cfg.StrOpt(
        "legacy_image_repository",
        default="docker.io/k8scloudprovider",
        help="Legacy image repository for the OpenStack Cinder CSI plugin.",
    ),
    cfg.StrOpt(
        "v1_22_image",
        default="$legacy_image_repository/cinder-csi-plugin:v1.22.2",
        help="Image for the OpenStack Cinder CSI plugin for Kubernetes v1.22.",
    ),
    cfg.StrOpt(
        "v1_23_image",
        default="$legacy_image_repository/cinder-csi-plugin:v1.23.4",
        help="Image for the OpenStack Cinder CSI plugin for Kubernetes v1.23.",
    ),
    cfg.StrOpt(
        "image_repository",
        default="registry.k8s.io/provider-os",
        help="Image repository for the OpenStack Cinder CSI plugin.",
    ),
    cfg.StrOpt(
        "v1_24_image",
        default="$image_repository/cinder-csi-plugin:v1.24.6",
        help="Image for the OpenStack Cinder CSI plugin for Kubernetes v1.24.",
    ),
    cfg.StrOpt(
        "v1_25_image",
        default="$image_repository/cinder-csi-plugin:v1.25.5",
        help="Image for the OpenStack Cinder CSI plugin for Kubernetes v1.25.",
    ),
    cfg.StrOpt(
        "v1_26_image",
        default="$image_repository/cinder-csi-plugin:v1.26.2",
        help="Image for the OpenStack Cinder CSI plugin for Kubernetes v1.26.",
    ),
]

CONF = cfg.CONF
CONF.register_opts(auto_scaling_opts, "auto_scaling")
CONF.register_opts(cinder_csi_opts, "cinder_csi")
CONF.register_opts(cloud_controller_manager_opts, "cloud_controller_manager")
CONF.register_opts(csi_opts, "csi")
