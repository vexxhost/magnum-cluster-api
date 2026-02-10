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

# This script tests Hydrophone with a kind cluster to understand the output
# paths and artifacts it generates. This is used to ensure the conformance
# workflow is correctly configured before running it on actual clusters.

HYDROPHONE_VERSION=${HYDROPHONE_VERSION:-v0.8.0}
KUBERNETES_VERSION=${KUBERNETES_VERSION:-v1.32.0}

# Install hydrophone if not already installed
if ! command -v hydrophone &> /dev/null; then
    echo "Installing hydrophone ${HYDROPHONE_VERSION}..."
    curl -LO "https://github.com/kubernetes-sigs/hydrophone/releases/download/${HYDROPHONE_VERSION}/hydrophone_$(uname -s)_$(uname -m).tar.gz"
    tar -xzf "hydrophone_$(uname -s)_$(uname -m).tar.gz"
    sudo mv hydrophone /usr/local/bin/
    rm "hydrophone_$(uname -s)_$(uname -m).tar.gz"
fi

# Create a kind cluster if it doesn't exist
if ! kind get clusters | grep -q "^hydrophone-test$"; then
    echo "Creating kind cluster for testing..."
    kind create cluster --name hydrophone-test --image "kindest/node:${KUBERNETES_VERSION}"
fi

# Get the kubeconfig for the kind cluster
kind export kubeconfig --name hydrophone-test

echo "Running hydrophone conformance tests..."
echo "This will take some time as it runs the full conformance test suite."

# Run hydrophone and capture the output directory
# NOTE: We're running with --conformance to generate CNCF-compliant artifacts
hydrophone --conformance --output-dir ./hydrophone-output

echo ""
echo "Hydrophone test completed. Output structure:"
find ./hydrophone-output -type f -ls

echo ""
echo "Expected artifacts for CNCF submission:"
echo "  - e2e.log: Full test logs"
echo "  - junit_01.xml: JUnit test results"
echo "  - PRODUCT.yaml: Product information file"
echo ""
echo "These files should be packaged and uploaded as GitHub artifacts"

# Clean up
echo "Cleaning up kind cluster..."
kind delete cluster --name hydrophone-test

echo ""
echo "Test completed successfully!"
echo "Use the output structure above to configure the conformance workflow."
