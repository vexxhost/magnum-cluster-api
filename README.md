# `magnum-cluster-api`

## Testing & Development

In order to be able to test and develop the `magnum-cluster-api` project, you
will need to have an existing Magnum deployment.

1. Clone the DevStack repository

   ```bash
   sudo mkdir -p /opt/stack
   sudo chown -Rv ${USER}. /opt/stack
   git clone https://opendev.org/openstack/devstack /opt/stack
   ```

2. Create a DevStack configuration file

   ```bash
   sudo apt-get update
   sudo apt-get install -y pwgen
   cat <<EOF > /opt/stack/local.conf
   [[local|localrc]]
   KEYSTONE_ADMIN_ENDPOINT=true
   DATABASE_PASSWORD=$(pwgen 32 1)
   RABBIT_PASSWORD=$(pwgen 32 1)
   SERVICE_PASSWORD=$(pwgen 32 1)
   ADMIN_PASSWORD=$(pwgen 32 1)
   LIBVIRT_TYPE=kvm
   VOLUME_BACKING_FILE_SIZE=50G
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
   ```

1. Start the DevStack deployment

   ```bash
   /opt/stack/stack.sh
   ```

1. Install the `kubectl` CLI:

   ```bash
   curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
   sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
   ```

1. Install Docker

   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```

1. Install the `kind` CLI:

   ```bash
   curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.16.0/kind-linux-amd64
   chmod +x ./kind
   sudo mv ./kind /usr/local/bin/kind
   ```

1. Create a local Kubernetes cluster using KinD:

   ```bash
   kind create cluster
   ```

1. Install the `clusterctl` CLI:

   ```bash
   curl -L https://github.com/kubernetes-sigs/cluster-api/releases/download/v1.2.5/clusterctl-linux-amd64 -o clusterctl
   chmod +x ./clusterctl
   sudo mv ./clusterctl /usr/local/bin/clusterctl
   clusterctl version
   ```

1. Enable the `ClusterResourceSet` feature gate and initialize all the
   necessary components:

   ```bash
    export EXP_CLUSTER_RESOURCE_SET=true
    clusterctl init --infrastructure openstack
    ```

1. Install the `magnum-cluster-api` project as an editable dependency in order
   to be able to test and develop it by running the following command inside
   the folder where you cloned the `magnum-cluster-api` project:

   ```bash
   pip install -e .
   ```

1. Restart all of the Magnum services to pick up the added plugin:

   ```bash
   sudo systemctl restart devstack@magnum-{api,cond}
   ```

1. Upload an image to use with Magnum

   ```bash
   TODO
   ```

1. Create a cluster template that uses the Cluster API driver

   ```bash
   openstack coe cluster template create \
     --image 2fe53e0a-4f77-4608-beb8-12fdc595c03b \
     --external-network public \
     --dns-nameserver 8.8.8.8 \
     --master-lb-enabled \
     --flavor m1.medium \
     --master-flavor m1.medium \
     --docker-volume-size 5 \
     --network-driver calico \
     --docker-storage-driver overlay2 \
     --coe kubernetes \
     k8s-cluster-template-capi
   ```

1. Spin up a new cluster using the Cluster API driver

   ```bash
   openstack coe cluster create \
     --cluster-template k8s-cluster-template-capi \
     --master-count 3 \
     --node-count 2 \
     k8s-cluster
   ```

1. Once the cluster reaches `CREATE_COMPLETE` state, you can interact with it:

   ```bash
   eval $(openstack coe cluster config k8s-cluster)
   ```

## TODO:
- audit all labels + options to make sure it works
- cluster resize
- cluster upgrade
- autohealing => https://cluster-api.sigs.k8s.io/tasks/automated-machine-management/healthchecking.html
- autoscaling => https://cluster-api.sigs.k8s.io/tasks/automated-machine-management/autoscaling.html
- pre-commit
- boot from volume
- custom image location
- ingress
- k8s_keystone_auth_tag
- kube_dashboard_enabled
- monitoring (maybe?)
