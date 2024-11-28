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

# XXX(mnaser): This is a workaround for when Cluster API is tagged but not
#              released yet.
export GOPROXY=off

# Versions to test
CAPI_VERSION=${CAPI_VERSION:-v1.8.4}
CAPO_VERSION=${CAPO_VERSION:-v0.11.2}

# Install the `clusterctl` CLI
sudo curl -Lo /usr/local/bin/clusterctl https://github.com/kubernetes-sigs/cluster-api/releases/download/${CAPI_VERSION}/clusterctl-linux-amd64
sudo chmod +x /usr/local/bin/clusterctl

# Initialize the `clusterctl` CLI
export EXP_CLUSTER_RESOURCE_SET=true
export EXP_KUBEADM_BOOTSTRAP_FORMAT_IGNITION=true #Used by the kubeadm bootstrap provider
export CLUSTER_TOPOLOGY=true
clusterctl init \
  --core cluster-api:${CAPI_VERSION} \
  --bootstrap kubeadm:${CAPI_VERSION} \
  --control-plane kubeadm:${CAPI_VERSION} \
  --infrastructure openstack:${CAPO_VERSION}

# Wait for components to go up
kubectl -n capi-kubeadm-bootstrap-system rollout status deploy/capi-kubeadm-bootstrap-controller-manager
kubectl -n capi-kubeadm-control-plane-system rollout status deploy/capi-kubeadm-control-plane-controller-manager
kubectl -n capi-system rollout status deploy/capi-controller-manager
kubectl -n capo-system rollout status deploy/capo-controller-manager
