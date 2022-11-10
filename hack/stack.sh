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

# Install Go 1.19
curl -Lo /tmp/go1.19.3.linux-amd64.tar.gz https://go.dev/dl/go1.19.3.linux-amd64.tar.gz
rm -rf /usr/local/go && sudo tar -C /usr/local -xzf /tmp/go1.19.3.linux-amd64.tar.gz

# Install drone/envsubst
/usr/local/go/bin/go install github.com/drone/envsubst/v2/cmd/envsubst@latest

# Initialize the `clusterctl` CLI
export EXP_CLUSTER_RESOURCE_SET=true
export CLUSTER_TOPOLOGY=true
curl -L https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.3.0-beta.1/core-components.yaml | $HOME/go/bin/envsubst | kubectl apply -f-
curl -L https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.3.0-beta.1/control-plane-components.yaml | $HOME/go/bin/envsubst | kubectl apply -f-
curl -L https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.3.0-beta.1/bootstrap-components.yaml | $HOME/go/bin/envsubst | kubectl apply -f-
curl -L https://storage.googleapis.com/artifacts.k8s-staging-capi-openstack.appspot.com/components/nightly_main_20221109/infrastructure-components.yaml | $HOME/go/bin/envsubst | kubectl apply -f-

# Install Skopeo
sudo curl -Lo /usr/local/bin/skopeo https://github.com/lework/skopeo-binary/releases/download/v1.10.0/skopeo-linux-amd64
sudo chmod +x /usr/local/bin/skopeo

# Install `magnum-cluster-api`
pip install -U setuptools pip
$HOME/.local/bin/pip3 install -e .

# Restart Magnum to pick-up new driver
sudo systemctl restart devstack@magnum-{api,cond}
