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


from magnum.common import exception
from magnum.i18n import _


class HelmException(Exception):
    pass


class HelmReleaseNotFound(HelmException):
    pass


class OpenStackClusterException(Exception):
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


class ClusterAPIReconcileTimeout(Exception):
    pass


class ClusterMasterCountEven(Exception):
    pass


class UnsupportedCNI(Exception):
    pass


class MachineInvalidName(exception.InvalidName):
    message = _("Expected a lowercase RFC 1123 subdomain name, got %(name)s.")


class MachineDeploymentNotFound(exception.ObjectNotFound):
    message = _("MachineDeployment %(name)s not found.")


class InvalidOctaviaLoadBalancerAlgorithm(exception.Invalid):
    message = _("Invalid value for octavia_lb_algorithm: %(octavia_lb_algorithm)s.")
