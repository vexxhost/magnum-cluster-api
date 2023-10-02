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

# This script will run the full functional tests for a given `KUBE_TAG`.  It
# will download the image, create a cluster, wait for it to hit `CREATE_COMPLETE`
# and then run `sonobuoy` against it.

source /opt/stack/openrc

OS_DISTRO=${OS_DISTRO:-ubuntu}
NODE_COUNT=${NODE_COUNT:-2}
SONOBUOY_VERSION=${SONOBUOY_VERSION:-0.56.16}
SONOBUOY_ARCH=${SONOBUOY_ARCH:-amd64}
DNS_NAMESERVER=${DNS_NAMESERVER:-1.1.1.1}

# Determine image name
[[ "${OS_DISTRO}" == "ubuntu" ]] && IMAGE_NAME="ubuntu-2204-kube-${KUBE_TAG}" || IMAGE_NAME="flatcar-kube-${KUBE_TAG}";

# If running inside GitHub Actions, use Azure's "168.63.129.16" for DNS
if [[ -n "${GITHUB_ACTIONS}" ]]; then
  DNS_NAMESERVER=168.63.129.16
fi

# If `BUILD_NEW_IMAGE` is true, then we use the provided artifact, otherwise
# we download the latest promoted image.
if [[ "${BUILD_NEW_IMAGE}" != "true" ]]; then
  curl -LO https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/${IMAGE_NAME}.qcow2
fi

# Upload image to Glance
openstack image create \
  --disk-format=qcow2 \
  --container-format=bare \
  --property os_distro=${OS_DISTRO} \
  --file=${IMAGE_NAME}.qcow2 \
  ${IMAGE_NAME}

# Create cluster template
openstack coe cluster template create \
    --image $(openstack image show ${IMAGE_NAME} -c id -f value) \
    --external-network public \
    --dns-nameserver ${DNS_NAMESERVER} \
    --master-lb-enabled \
    --master-flavor m1.medium \
    --flavor m1.medium \
    --network-driver calico \
    --docker-storage-driver overlay2 \
    --coe kubernetes \
    --label kube_tag=${KUBE_TAG} \
    --label fixed_subnet_cidr=192.168.24.0/24 \
    k8s-${KUBE_TAG};

# Create cluster
openstack coe cluster create \
  --cluster-template k8s-${KUBE_TAG} \
  --master-count 1 \
  --node-count ${NODE_COUNT} \
  k8s-cluster

# Wait for cluster to be "CREATE_COMPLETE".
for i in {1..240}; do
  CLUSTER_STATUS=$(openstack coe cluster show k8s-cluster -c status -f value)
  if [[ ${CLUSTER_STATUS} == *"FAILED"* ]]; then
    echo "Cluster failed to create"
    exit 1
  elif [[ ${CLUSTER_STATUS} == *"CREATE_COMPLETE"* ]]; then
    echo "Cluster created"
    break
  else
    echo "Cluster status: ${CLUSTER_STATUS}"
    sleep 5
  fi
done

# Get the cluster configuration file
eval $(openstack coe cluster config k8s-cluster)

# Download sonobuoy
curl -LO https://github.com/vmware-tanzu/sonobuoy/releases/download/v${SONOBUOY_VERSION}/sonobuoy_${SONOBUOY_VERSION}_linux_${SONOBUOY_ARCH}.tar.gz
tar -xzf sonobuoy_${SONOBUOY_VERSION}_linux_${SONOBUOY_ARCH}.tar.gz

# Run sonobuoy
./sonobuoy run --wait --mode certified-conformance --plugin-env=e2e.E2E_PARALLEL=true

# Retrieve results
RESULTS_FILE=$(./sonobuoy retrieve --filename sonobuoy-results.tar.gz)

# Print results
./sonobuoy results ${RESULTS_FILE}

# Fail if the Sonobuoy tests failed
if ! ./sonobuoy results --plugin e2e ${RESULTS_FILE} | grep -q "Status: passed"; then
  echo "Sonobuoy tests failed"
  exit 1
fi
