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
    git clone https://git.openstack.org/openstack-dev/devstack /opt/stack
else
    pushd /opt/stack
    git pull
    popd
fi

# Create DevStack configuration file
cat <<EOF > /opt/stack/local.conf
[[local|localrc]]
# General
GIT_BASE=https://github.com

# Secrets
DATABASE_PASSWORD=root
RABBIT_PASSWORD=secrete123
SERVICE_PASSWORD=secrete123
ADMIN_PASSWORD=secrete123

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
kubernetes_allowed_network_drivers = calico
kubernetes_default_network_driver = calico
EOF

# Start DevStack deployment
/opt/stack/stack.sh

# Install `kubectl` CLI
curl -Lo /tmp/kubectl "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 /tmp/kubectl /usr/local/bin/kubectl

# Install `helm` CLI
curl -Lo /tmp/helm.tar.gz "https://get.helm.sh/helm-v3.10.3-linux-amd64.tar.gz"
tar -zxvf /tmp/helm.tar.gz -C /tmp
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
rm -rf /tmp/helm.tar.gz /tmp/linux-amd64/

# Install Docker
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sudo sh /tmp/get-docker.sh
sudo usermod -aG docker $USER

# Docker tinks with firewalls
sudo iptables -I DOCKER-USER -j ACCEPT

# Install `kind` CLI
sudo curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/v0.16.0/kind-linux-amd64
sudo chmod +x /usr/local/bin/kind

# Create a `kind` cluster inside "docker" group
newgrp docker <<EOF
kind create cluster
EOF

# Label a control plane node
kubectl label node kind-control-plane openstack-control-plane=enabled

# Install the `clusterctl` CLI
sudo curl -Lo /usr/local/bin/clusterctl https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.4.4/clusterctl-linux-amd64
sudo chmod +x /usr/local/bin/clusterctl

# Initialize the `clusterctl` CLI
export EXP_CLUSTER_RESOURCE_SET=true
export CLUSTER_TOPOLOGY=true
clusterctl init \
  --core cluster-api:v1.4.4 \
  --bootstrap kubeadm:v1.4.4 \
  --control-plane kubeadm:v1.4.4 \
  --infrastructure openstack:v0.7.1

# Vendor the chart
make vendor

# Install `magnum-cluster-api`
pip install -U setuptools pip
$HOME/.local/bin/pip3 install -e .

# Restart Magnum to pick-up new driver
sudo systemctl restart devstack@magnum-{api,cond}
