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

# Install dependencies
sudo apt-get update
sudo apt-get install -y pwgen

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
KEYSTONE_ADMIN_ENDPOINT=true
DATABASE_PASSWORD=secrete123
RABBIT_PASSWORD=secrete123
SERVICE_PASSWORD=secrete123
ADMIN_PASSWORD=secrete123
LIBVIRT_TYPE=kvm
VOLUME_BACKING_FILE_SIZE=50G
GLANCE_LIMIT_IMAGE_SIZE_TOTAL=10000
enable_plugin barbican https://opendev.org/openstack/barbican
enable_plugin heat https://opendev.org/openstack/heat
enable_plugin neutron https://opendev.org/openstack/neutron
enable_plugin magnum https://opendev.org/openstack/magnum
enable_plugin magnum-ui https://opendev.org/openstack/magnum-ui
enable_plugin octavia https://opendev.org/openstack/octavia
enable_service octavia
enable_service o-cw
enable_service o-api
enable_service o-hk
enable_service o-hm
[[post-config|/etc/neutron/neutron.conf]]
[DEFAULT]
advertise_mtu = True
global_physnet_mtu = 1400

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
sudo curl -Lo /usr/local/bin/clusterctl https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.3.2/clusterctl-linux-amd64
sudo chmod +x /usr/local/bin/clusterctl

# Initialize the `clusterctl` CLI
export EXP_CLUSTER_RESOURCE_SET=true
export CLUSTER_TOPOLOGY=true
clusterctl init \
  --core cluster-api:v1.3.3 \
  --bootstrap kubeadm:v1.3.3 \
  --control-plane kubeadm:v1.3.3 \
  --infrastructure openstack:v0.7.0

# Install Skopeo
sudo curl -Lo /usr/local/bin/skopeo https://github.com/lework/skopeo-binary/releases/download/v1.10.0/skopeo-linux-amd64
sudo chmod +x /usr/local/bin/skopeo

# Install Flux
curl -s https://fluxcd.io/install.sh | sudo bash
flux install

# Install `magnum-cluster-api`
pip install -U setuptools pip
$HOME/.local/bin/pip3 install -e .

# Restart Magnum to pick-up new driver
sudo systemctl restart devstack@magnum-{api,cond}
