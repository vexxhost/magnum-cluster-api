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

from magnum.i18n import _
from oslo_config import cfg

auto_scaling_group = cfg.OptGroup(name="auto_scaling", title="Options for auto scaling")

capi_client_group = cfg.OptGroup(
    name="capi_client", title="Options for the Cluster API client"
)

manila_client_group = cfg.OptGroup(
    name="manila_client", title="Options for the Manila client"
)

proxy_group = cfg.OptGroup(name="proxy", title="Options for Cluster API proxy")


auto_scaling_opts = [
    cfg.StrOpt(
        "image_repository",
        default="registry.k8s.io/autoscaling",
        help="Image repository for the cluster auto-scaler.",
    ),
    cfg.StrOpt(
        "v1_22_image",
        default="$image_repository/cluster-autoscaler:v1.22.3",
        help="Image for the cluster auto-scaler for Kubernetes v1.22.",
    ),
    cfg.StrOpt(
        "v1_23_image",
        default="$image_repository/cluster-autoscaler:v1.23.1",
        help="Image for the cluster auto-scaler for Kubernetes v1.23.",
    ),
    cfg.StrOpt(
        "v1_24_image",
        default="$image_repository/cluster-autoscaler:v1.24.2",
        help="Image for the cluster auto-scaler for Kubernetes v1.24.",
    ),
    cfg.StrOpt(
        "v1_25_image",
        default="$image_repository/cluster-autoscaler:v1.25.2",
        help="Image for the cluster auto-scaler for Kubernetes v1.25.",
    ),
    cfg.StrOpt(
        "v1_26_image",
        default="$image_repository/cluster-autoscaler:v1.26.3",
        help="Image for the cluster auto-scaler for Kubernetes v1.26.",
    ),
    cfg.StrOpt(
        "v1_27_image",
        default="$image_repository/cluster-autoscaler:v1.27.2",
        help="Image for the cluster auto-scaler for Kubernetes v1.27.",
    ),
    cfg.StrOpt(
        "v1_28_image",
        default="$image_repository/cluster-autoscaler:v1.28.5",
        help="Image for the cluster auto-scaler for Kubernetes v1.28.",
    ),
    cfg.StrOpt(
        "v1_29_image",
        default="$image_repository/cluster-autoscaler:v1.29.3",
        help="Image for the cluster auto-scaler for Kubernetes v1.29.",
    ),
    cfg.StrOpt(
        "v1_30_image",
        default="$image_repository/cluster-autoscaler:v1.30.1",
        help="Image for the cluster auto-scaler for Kubernetes v1.30.",
    ),
    cfg.StrOpt(
        "v1_31_image",
        default="$image_repository/cluster-autoscaler:v1.31.0",
        help="Image for the cluster auto-scaler for Kubernetes v1.31.",
    ),
]


capi_client_opts = [
    cfg.StrOpt(
        "endpoint_type",
        default="publicURL",
        help=_(
            "Type of endpoint in Identity service catalog to use "
            "for communication with the OpenStack service."
        ),
    ),
]


manila_client_opts = [
    cfg.StrOpt(
        "region_name",
        help=_(
            "Region in Identity service catalog to use for "
            "communication with the OpenStack service."
        ),
    ),
    cfg.StrOpt(
        "endpoint_type",
        default="publicURL",
        help=_(
            "Type of endpoint in Identity service catalog to use "
            "for communication with the OpenStack service."
        ),
    ),
    cfg.StrOpt(
        "api_version",
        default="3",
        help=_("Version of Manila API to use in manilaclient."),
    ),
]


proxy_opts = [
    cfg.StrOpt(
        "haproxy_pid_path",
        default="/var/run/haproxy.pid",
        help=_("Path to HAProxy PID file."),
    ),
]


common_security_opts = [
    cfg.StrOpt("ca_file", help=_("Optional CA cert file to use in SSL connections.")),
    cfg.StrOpt("cert_file", help=_("Optional PEM-formatted certificate chain file.")),
    cfg.StrOpt(
        "key_file",
        help=_("Optional PEM-formatted file that contains the " "private key."),
    ),
    cfg.BoolOpt(
        "insecure",
        default=False,
        help=_("If set, then the server's certificate will not " "be verified."),
    ),
]

ALL_GROUPS = [
    auto_scaling_group,
    capi_client_group,
    manila_client_group,
    proxy_group,
]

ALL_OPTS = [
    (auto_scaling_group, auto_scaling_opts),
    (capi_client_group, capi_client_opts),
    (capi_client_group, common_security_opts),
    (manila_client_group, manila_client_opts),
    (manila_client_group, common_security_opts),
    (proxy_group, proxy_opts),
]


CONF = cfg.CONF

for group in ALL_GROUPS:
    CONF.register_group(group)

for group, opts in ALL_OPTS:
    CONF.register_opts(opts, group=group)


def list_opts():
    return ALL_OPTS
