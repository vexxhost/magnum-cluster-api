#!/usr/bin/env bash

# SPDX-License-Identifier: Apache-2.0

set -o pipefail
set -o errexit
set -o nounset

if grep -q "KubeProxyConfiguration" /run/kubeadm/kubeadm.yaml; then
    exit 0
fi

cat <<EOF >> /run/kubeadm/kubeadm.yaml
---
apiVersion: kubeproxy.config.k8s.io/v1alpha1
kind: KubeProxyConfiguration
metricsBindAddress: "0.0.0.0:10249"
EOF
