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
   export OS_DISTRO=ubuntu
   export IMAGE_FAMILY=ubuntu-24.04
   for version in v1.33.12 v1.34.8 v1.35.5 v1.36.1; do \
      IMAGE_NAME="${IMAGE_FAMILY}-${version}"; \
      curl -LO https://github.com/vexxhost/capo-image-elements/releases/latest/download/${IMAGE_NAME}.qcow2; \
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
