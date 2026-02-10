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

# This script runs Kubernetes conformance tests using Hydrophone.
# It creates a cluster, runs the conformance tests, and collects the artifacts
# required for CNCF Kubernetes conformance certification.

NODE_COUNT=${NODE_COUNT:-2}
NETWORK_DRIVER=${NETWORK_DRIVER:-calico}
HYDROPHONE_VERSION=${HYDROPHONE_VERSION:-v0.8.0}
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
    k8s-conformance-${KUBE_TAG};

# Create cluster
openstack coe cluster create \
  --cluster-template $(openstack coe cluster template show -c uuid -f value k8s-conformance-${KUBE_TAG}) \
  --master-count 1 \
  --node-count ${NODE_COUNT} \
  --merge-labels \
  --label audit_log_enabled=true \
  k8s-conformance-cluster

# Wait for cluster creation to be queued
set +e
for i in {1..5}; do
  openstack coe cluster show k8s-conformance-cluster 2>&1
  exit_status=$?
  if [ $exit_status -eq 0 ]; then
      break
  else
      echo "Error: Cluster k8s-conformance-cluster could not be found."
      sleep 1
  fi
done
set -e

# Wait for cluster to be "CREATE_COMPLETE".
for i in {1..240}; do
  CLUSTER_STATUS=$(openstack coe cluster show k8s-conformance-cluster -c status -f value)
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
eval $(openstack coe cluster config k8s-conformance-cluster)

# Install hydrophone if not already installed
if ! command -v hydrophone &> /dev/null; then
    echo "Installing hydrophone ${HYDROPHONE_VERSION}..."
    curl -LO "https://github.com/kubernetes-sigs/hydrophone/releases/download/${HYDROPHONE_VERSION}/hydrophone_$(uname -s)_$(uname -m).tar.gz"
    tar -xzf "hydrophone_$(uname -s)_$(uname -m).tar.gz"
    chmod +x hydrophone
    sudo mv hydrophone /usr/local/bin/
    rm "hydrophone_$(uname -s)_$(uname -m).tar.gz" || true
fi

# Create output directory for conformance results
OUTPUT_DIR="./conformance-results"
mkdir -p ${OUTPUT_DIR}

echo "Running Kubernetes conformance tests with Hydrophone..."
echo "This will run the full conformance test suite required for CNCF certification."
echo "This process may take several hours to complete."

# Run hydrophone conformance tests
# --conformance flag ensures it runs the official conformance test suite
# --output-dir specifies where to save the artifacts
hydrophone --conformance --output-dir ${OUTPUT_DIR}

echo ""
echo "Conformance tests completed!"
echo ""
echo "Generated artifacts:"
ls -lh ${OUTPUT_DIR}/

# Verify that required files exist
REQUIRED_FILES=("e2e.log" "junit_01.xml")
for file in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "${OUTPUT_DIR}/${file}" ]; then
    echo "Error: Required file ${file} not found in ${OUTPUT_DIR}"
    exit 1
  fi
done

echo ""
echo "All required conformance artifacts have been generated successfully."
echo "These artifacts can be submitted to CNCF for Kubernetes conformance certification."

# Create a tarball of all conformance results for easy upload
tar -czf conformance-results.tar.gz -C ${OUTPUT_DIR} .

echo ""
echo "Conformance results archived to: conformance-results.tar.gz"
