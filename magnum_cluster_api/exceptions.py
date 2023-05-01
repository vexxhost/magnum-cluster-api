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


class HelmException(Exception):
    pass


class HelmReleaseNotFound(HelmException):
    pass


class ClusterException(Exception):
    pass


class ClusterNotReady(ClusterException):
    pass


class ClusterEndpointNotReady(ClusterNotReady):
    message = "Cluster endpoint is not ready"


class ClusterVersionNotReady(ClusterNotReady):
    message = "Cluster version is not ready"


class ClusterKubeConfigNotReady(ClusterNotReady):
    message = "Cluster KUBECONFIG is not ready"


class OpenStackClusterException(ClusterException):
    pass


class OpenStackClusterNotCreated(OpenStackClusterException):
    pass


class OpenStackClusterNotReady(OpenStackClusterException):
    pass


class OpenStackClusterExternalNetworkNotReady(OpenStackClusterNotReady):
    pass


class OpenStackClusterNetworkNotReady(OpenStackClusterNotReady):
    pass


class OpenStackClusterSubnetNotReady(OpenStackClusterNotReady):
    pass
