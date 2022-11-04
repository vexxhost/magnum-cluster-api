#!/bin/bash -xe

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

# Install the `clusterctl` CLI
sudo curl -Lo /usr/local/bin/clusterctl https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.2.4/clusterctl-linux-amd64
sudo chmod +x /usr/local/bin/clusterctl
clusterctl version

# Initialize the `clusterctl` CLI
export EXP_CLUSTER_RESOURCE_SET=true
clusterctl init --infrastructure openstack

# Install `magnum-cluster-api`
pip install -U setuptools pip
$HOME/.local/bin/pip3 install -e .

# Restart Magnum to pick-up new driver
sudo systemctl restart devstack@magnum-{api,cond}
