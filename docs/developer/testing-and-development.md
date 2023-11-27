# Testing & Development

In order to be able to test and develop the `magnum-cluster-api` project, you
will need to have an existing Magnum deployment.  You can use the following
steps to be able to test and develop the project.

1. Start up a DevStack environment with all Cluster API dependencies

   ```bash
   ./hack/stack.sh
   ```

1. Upload an image to use with Magnum and create cluster templates

   ```bash
   pushd /tmp
   source /opt/stack/openrc
   export OS_DISTRO=ubuntu # you can change this to "flatcar" if you want to use Flatcar
   for version in v1.24.16 v1.25.12 v1.26.7 v1.27.4; do \
      [[ "${OS_DISTRO}" == "ubuntu" ]] && IMAGE_NAME="ubuntu-2204-kube-${version}" || IMAGE_NAME="flatcar-kube-${version}"; \
      curl -LO https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/${IMAGE_NAME}.qcow2; \
      openstack image create ${IMAGE_NAME} --disk-format=qcow2 --container-format=bare --property os_distro=${OS_DISTRO} --file=${IMAGE_NAME}.qcow2; \
      openstack coe cluster template create \
        --image $(openstack image show ${IMAGE_NAME} -c id -f value) \
        --external-network public \
        --dns-nameserver 8.8.8.8 \
        --master-lb-enabled \
        --master-flavor m1.medium \
        --flavor m1.medium \
        --network-driver calico \
        --docker-storage-driver overlay2 \
        --coe kubernetes \
        --label kube_tag=${version} \
        k8s-${version};
   done;
   popd
   ```

1. Spin up a new cluster using the Cluster API driver

   ```bash
   openstack coe cluster create \
     --cluster-template k8s-v1.25.12 \
     --master-count 3 \
     --node-count 2 \
     k8s-v1.25.12
   ```

1. Once the cluster reaches `CREATE_COMPLETE` state, you can interact with it:

   ```bash
   eval $(openstack coe cluster config k8s-v1.25.12)
   ```
