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
# and then run `hydrophone` against it.

NODE_COUNT=${NODE_COUNT:-2}
NETWORK_DRIVER=${NETWORK_DRIVER:-calico}
HYDROPHONE_VERSION=${HYDROPHONE_VERSION:-v0.7.0}
HYDROPHONE_ARCH=${HYDROPHONE_ARCH:-x86_64}
DNS_NAMESERVER=${DNS_NAMESERVER:-1.1.1.1}

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
    --label octavia_provider=ovn \
    k8s-${KUBE_TAG};

# Create cluster
openstack coe cluster create \
  --cluster-template $(openstack coe cluster template show -c uuid -f value k8s-${KUBE_TAG}) \
  --master-count 1 \
  --node-count ${NODE_COUNT} \
  --merge-labels \
  --label audit_log_enabled=true \
  k8s-cluster

# Wait for cluster creation to be queued
set +e
for i in {1..5}; do
  openstack coe cluster show k8s-cluster 2>&1
  exit_status=$?
  if [ $exit_status -eq 0 ]; then
      break
  else
      echo "Error: Cluster k8s-cluster could not be found."
      sleep 1
  fi
done
set -e

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

# Download hydrophone
curl -LO https://github.com/kubernetes-sigs/hydrophone/releases/download/${HYDROPHONE_VERSION}/hydrophone_Linux_${HYDROPHONE_ARCH}.tar.gz
tar -xzf hydrophone_Linux_${HYDROPHONE_ARCH}.tar.gz

# Run hydrophone conformance tests
# Note: Conformance tests typically take 1-2 hours to complete
./hydrophone --conformance --output-dir=./hydrophone-results --parallel $(nproc)

# Check if tests passed by examining the junit file
# Verify that:
# 1. Tests were actually run (tests attribute > 0)
# 2. No failures occurred (failures="0")
# 3. No errors occurred (errors="0")
if ! grep -q 'errors="0"' ./hydrophone-results/junit_01.xml; then
  echo "Hydrophone conformance tests had errors"
  cat ./hydrophone-results/e2e.log
  exit 1
fi

if ! grep -q 'failures="0"' ./hydrophone-results/junit_01.xml; then
  echo "Hydrophone conformance tests failed"
  cat ./hydrophone-results/e2e.log
  exit 1
fi

# Extract and validate the test count to ensure tests actually ran
TEST_COUNT=$(sed -nE 's/.*tests="([0-9]+)".*/\1/p' ./hydrophone-results/junit_01.xml | head -1)
if [[ -z "$TEST_COUNT" ]] || [[ "$TEST_COUNT" -eq 0 ]]; then
  echo "No Hydrophone conformance tests were run"
  cat ./hydrophone-results/e2e.log
  exit 1
fi

echo "Hydrophone conformance tests passed ($TEST_COUNT tests)"

# Create a tarball of results for archival (similar to sonobuoy)
tar -czf hydrophone-results.tar.gz -C hydrophone-results .
