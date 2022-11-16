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

# Label a control plane node
kubectl label node kind-control-plane openstack-control-plane=enabled

# Initialize the `clusterctl` CLI
export EXP_CLUSTER_RESOURCE_SET=true
export CLUSTER_TOPOLOGY=true
clusterctl init \
   --core cluster-api:v1.3.0-rc.0 \
   --bootstrap kubeadm:v1.3.0-rc.0 \
   --control-plane kubeadm:v1.3.0-rc.0
curl -L https://storage.googleapis.com/artifacts.k8s-staging-capi-openstack.appspot.com/components/nightly_main_20221109/infrastructure-components.yaml | kubectl apply -f-

# Install Skopeo
sudo curl -Lo /usr/local/bin/skopeo https://github.com/lework/skopeo-binary/releases/download/v1.10.0/skopeo-linux-amd64
sudo chmod +x /usr/local/bin/skopeo

# Install Flux
curl -s https://fluxcd.io/install.sh | sudo bash
flux install

# Install `magnum-cluster-api`
pip install -U setuptools pip
$HOME/.local/bin/pip3 install -e .

# Install Flux
curl -Lo /tmp/flux_0.32.0_linux_amd64.tar.gz https://github.com/fluxcd/flux2/releases/download/v0.32.0/flux_0.32.0_linux_amd64.tar.gz
rm -rf $HOME/.local/bin/flux && sudo tar -C $HOME/.local/bin -xzf /tmp/flux_0.32.0_linux_amd64.tar.gz

# Node labeling
kubectl label node --all openstack-control-plane=enabled

# Restart Magnum to pick-up new driver
sudo systemctl restart devstack@magnum-{api,cond}
