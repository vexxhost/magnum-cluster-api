#!/bin/bash -xe

# Copyright (c) 2024 VEXXHOST, Inc.
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

# This script will run the full functional tests for a given `KUBE_TAG`.  It
# will download the image, create a cluster, wait for it to hit `CREATE_COMPLETE`
# and then run `sonobuoy` against it.

source /opt/stack/openrc admin admin

OS_DISTRO=${OS_DISTRO:-ubuntu}
IMAGE_OS=${IMAGE_OS:-ubuntu-2204}
NETWORK_DRIVER=${NETWORK_DRIVER:-calico}
DNS_NAMESERVER=${DNS_NAMESERVER:-1.1.1.1}
UPGRADE_KUBE_TAG=${UPGRADE_KUBE_TAG:-KUBE_TAG}
IMAGE_NAME="${IMAGE_OS}-kube-${KUBE_TAG}"
UPGRADE_IMAGE_NAME="${IMAGE_OS}-kube-${UPGRADE_KUBE_TAG}"

# If `BUILD_NEW_IMAGE` is true, then we use the provided artifact, otherwise
# we download the latest promoted image.
if [[ "${BUILD_NEW_IMAGE,,}" != "true" ]]; then
  curl -LO https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/${IMAGE_NAME}.qcow2
else
  test -f ${IMAGE_NAME}.qcow2 || exit 1
fi

# Upload image to Glance
openstack image create \
  --disk-format=qcow2 \
  --public \
  --container-format=bare \
  --property os_distro=${OS_DISTRO} \
  --file=${IMAGE_NAME}.qcow2 \
  ${IMAGE_NAME}

if [[ ${UPGRADE_KUBE_TAG} != ${KUBE_TAG} ]]; then
    if [[ "${BUILD_NEW_UPGRADE_IMAGE,,}" != "true" ]]; then
      curl -LO https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/${UPGRADE_IMAGE_NAME}.qcow2
    else
      test -f ${UPGRADE_IMAGE_NAME}.qcow2 || exit 1
    fi
    # Upload Upgrade image to Glance
    openstack image create \
      --disk-format=qcow2 \
      --public \
      --container-format=bare \
      --property os_distro=${OS_DISTRO} \
      --file=${UPGRADE_IMAGE_NAME}.qcow2 \
      ${UPGRADE_IMAGE_NAME}
fi

mkdir /tmp/magnum-nodes

pushd /opt/stack/tempest
echo "Tempest configs:"

cat <<EOF >> /opt/stack/tempest/etc/tempest.conf

[magnum]
flavor_id = m1.large
master_flavor_id = m1.large
copy_logs = true
network_driver = ${NETWORK_DRIVER}
image_id = ${IMAGE_OS}-kube-${KUBE_TAG}
coe = kubernetes
labels = '{"kube_tag": "${KUBE_TAG}", "fixed_subnet_cidr": "10.0.0.0/26"}'
docker_storage_driver = overlay

EOF

if [ ! -d /opt/stack/magnum-tempest-plugin ]; then
    git clone https://github.com/openstack/magnum-tempest-plugin /opt/stack/magnum-tempest-plugin
fi

# install magnum-tempest-plugin
pushd /opt/stack/magnum-tempest-plugin
$HOME/.local/bin/pip3 install -e .
popd

echo "Run Tempest against configs:"
cat /opt/stack/tempest/etc/tempest.conf

echo "Run Tempest tests:"
/opt/stack/data/venv/bin/tempest run -r '(^magnum_tempest_plugin)' \
    --exclude-regex '^magnum_tempest_plugin.tests.api.v1.test_cluster.ClusterTest.test_create_cluster_with_zero_nodes'
popd


if [[ ${UPGRADE_KUBE_TAG} != ${KUBE_TAG} ]]; then

    # Create cluster template
    openstack coe cluster template create \
        --image $(openstack image show ${IMAGE_NAME} -c id -f value) \
        --external-network public \
        --dns-nameserver ${DNS_NAMESERVER} \
        --master-lb-enabled \
        --master-flavor m1.large \
        --flavor m1.large \
        --network-driver ${NETWORK_DRIVER} \
        --docker-storage-driver overlay2 \
        --coe kubernetes \
        --label kube_tag=${KUBE_TAG} \
        --label fixed_subnet_cidr=192.168.24.0/24 \
        k8s-${KUBE_TAG};

    # Create cluster template for upgrade
    openstack coe cluster template create \
        --image $(openstack image show ${UPGRADE_IMAGE_NAME} -c id -f value) \
        --external-network public \
        --dns-nameserver ${DNS_NAMESERVER} \
        --master-lb-enabled \
        --master-flavor m1.large \
        --flavor m1.large \
        --network-driver ${NETWORK_DRIVER} \
        --docker-storage-driver overlay2 \
        --coe kubernetes \
        --label kube_tag=${UPGRADE_KUBE_TAG} \
        --label fixed_subnet_cidr=192.168.24.0/24 \
        k8s-${UPGRADE_KUBE_TAG};

    # Create cluster
    openstack coe cluster create \
      --cluster-template k8s-${KUBE_TAG} \
      --master-count 1 \
      --node-count 1 \
      --merge-labels \
      --label audit_log_enabled=true \
      k8s-cluster-upgrade

    # Wait for cluster creation to be queued
    set +e
    for i in {1..5}; do
      openstack coe cluster show k8s-cluster-upgrade 2>&1
      exit_status=$?
      if [ $exit_status -eq 0 ]; then
          break
      else
          echo "Error: Cluster k8s-cluster-upgrade could not be found."
          sleep 1
      fi
    done
    set -e

    # Wait for cluster to be "CREATE_COMPLETE".
    for i in {1..240}; do
      CLUSTER_STATUS=$(openstack coe cluster show k8s-cluster-upgrade -c status -f value)
      if [[ ${CLUSTER_STATUS} == *"FAILED"* ]]; then
        echo "Cluster failed to create"
        exit 1
      elif [[ ${CLUSTER_STATUS} == *"CREATE_COMPLETE"* ]]; then
        echo "Cluster created"
        break
      else
        echo "Currtny retry count: $i"
        echo "Cluster status: ${CLUSTER_STATUS}"
        sleep 5
      fi
    done

    # Upgrade cluster
    openstack coe cluster upgrade k8s-cluster-upgrade k8s-${UPGRADE_KUBE_TAG}
    # Wait for cluster to be "UPDATE_COMPLETE".
    for i in {1..240}; do
      CLUSTER_STATUS=$(openstack coe cluster show k8s-cluster-upgrade -c status -f value)
      if [[ ${CLUSTER_STATUS} == *"FAILED"* ]]; then
        echo "Cluster failed to upgrade"
        exit 1
      elif [[ ${CLUSTER_STATUS} == *"UPDATE_COMPLETE"* ]]; then
        echo "Cluster upgraded"
        exit 0
        break
      else
        echo "Currtny retry count: $i"
        echo "Cluster status: ${CLUSTER_STATUS}"
        sleep 5
      fi
    done
    exit 1
fi
