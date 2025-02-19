#!/bin/bash -xe

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

# Setup folders for DevStack
sudo mkdir -p /opt/stack
sudo chown -R ${USER}. /opt/stack

# Clone repository if not present, otherwise update
if [ ! -f /opt/stack/stack.sh ]; then
    git clone https://github.com/openstack/devstack /opt/stack
else
    pushd /opt/stack
    git pull
    popd
fi

# Backport Magnum trusts fix
pushd /opt/stack
git clone https://github.com/openstack/magnum
cd magnum
git fetch https://review.opendev.org/openstack/magnum refs/changes/15/940815/1 && git checkout FETCH_HEAD
popd

# Create DevStack configuration file
cat <<EOF > /opt/stack/local.conf
[[local|localrc]]
# General
GIT_BASE=https://github.com
RECLONE=no

# Secrets
DATABASE_PASSWORD=root
RABBIT_PASSWORD=secrete123
SERVICE_PASSWORD=secrete123
ADMIN_PASSWORD=secrete123

# OSCaaS
enable_service openstack-cli-server

# Keystone
KEYSTONE_ADMIN_ENDPOINT=true

# Glance
GLANCE_LIMIT_IMAGE_SIZE_TOTAL=10000

# Cinder
VOLUME_BACKING_FILE_SIZE=50G

# Nova
LIBVIRT_TYPE=kvm

# Neutron
enable_plugin neutron https://opendev.org/openstack/neutron
FIXED_RANGE=10.1.0.0/20

# Barbican
enable_plugin barbican https://opendev.org/openstack/barbican

# Octavia
enable_plugin octavia https://opendev.org/openstack/octavia
enable_plugin ovn-octavia-provider https://opendev.org/openstack/ovn-octavia-provider
enable_service octavia o-api o-cw o-hm o-hk o-da

# Magnum
enable_plugin magnum https://opendev.org/openstack/magnum
enable_plugin magnum-ui https://opendev.org/openstack/magnum-ui

# Manila
LIBS_FROM_GIT=python-manilaclient
enable_plugin manila https://opendev.org/openstack/manila
enable_plugin manila-ui https://opendev.org/openstack/manila-ui
enable_plugin manila-tempest-plugin https://opendev.org/openstack/manila-tempest-plugin

SHARE_DRIVER=manila.share.drivers.generic.GenericShareDriver
MANILA_ENABLED_BACKENDS=generic
MANILA_OPTGROUP_generic_driver_handles_share_servers=True
MANILA_OPTGROUP_generic_connect_share_server_to_tenant_network=True
MANILA_DEFAULT_SHARE_TYPE_EXTRA_SPECS='snapshot_support=True create_share_from_snapshot_support=True'
MANILA_CONFIGURE_DEFAULT_TYPES=True

MANILA_SERVICE_IMAGE_ENABLED=True
MANILA_USE_SERVICE_INSTANCE_PASSWORD=True

[[post-config|/etc/magnum/magnum.conf]]
[cluster_template]
kubernetes_allowed_network_drivers = calico,cilium
kubernetes_default_network_driver = calico
[nova_client]
api_version = 2.15
EOF

# Start DevStack deployment
/opt/stack/stack.sh

# Install "kubectl"
./hack/setup-kubectl.sh

# Install Helm
./hack/setup-helm.sh

# Install Docker
./hack/setup-docker.sh

# Install KinD
./hack/setup-kind.sh

# Install CAPI/CAPO
./hack/setup-capo.sh

# Install `magnum-cluster-api`
pip install -U setuptools pip python-magnumclient
$HOME/.local/bin/pip3 install -e .

# Restart Magnum to pick-up new driver
sudo systemctl restart devstack@magnum-{api,cond}
