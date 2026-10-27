CAPI_VERSION=${CAPI_VERSION:-v1.13.2}
CAPO_VERSION=${CAPO_VERSION:-v0.14.4}
ORC_VERSION=${ORC_VERSION:-v2.2.0}
CSR_APPROVER_VERSION=${CSR_APPROVER_VERSION:-v0.1.0}
KIND_VERSION=${KIND_VERSION:-v0.16.0}
HELM_VERSION=${HELM_VERSION:-v3.10.3}

MAGNUM_CLUSTER_API_REPO=${MAGNUM_CLUSTER_API_REPO:-https://github.com/vexxhost/magnum-cluster-api.git}
MAGNUM_CLUSTER_API_BRANCH=${MAGNUM_CLUSTER_API_BRANCH:-main}
MAGNUM_CLUSTER_API_DIR=$DEST/magnum-cluster-api

function ensure_kind_cluster {
  if echo "kind get clusters" | newgrp docker | grep -q kind; then
    echo "KinD cluster already exists, skipping creation"
    return
  fi

  echo "kind create cluster" | newgrp docker
  kubectl label node kind-control-plane openstack-control-plane=enabled
}

# Register `cluster-api-csr-approver` as a clusterctl add-on provider, it
# approves kubelet serving certificates for `kubelet_serving_tls_enabled=true`.
function write_clusterctl_config {
  cat <<EOF > $1
providers:
  - name: csr-approver
    type: AddonProvider
    url: https://github.com/vexxhost/cluster-api-csr-approver/releases/latest/addon-components.yaml
EOF
}

if is_service_enabled magnum-cluster-api; then

  if [[ "$1" == "stack" && "$2" == "pre-install" ]]; then
    # Install binaries
    sudo install -o root -g root -m 0755 \
      $(get_extra_file https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl) \
      /usr/local/bin/kubectl
    sudo install -o root -g root -m 0755 \
      $(get_extra_file https://github.com/kubernetes-sigs/cluster-api/releases/download/${CAPI_VERSION}/clusterctl-linux-amd64) \
      /usr/local/bin/clusterctl
    sudo install -o root -g root -m 0755 \
      $(get_extra_file https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64) \
      /usr/local/bin/kind
    # Install Helm
    tar -xvzf \
      $(get_extra_file https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz) \
      -C /tmp
    sudo install -o root -g root -m 0755 \
      /tmp/linux-amd64/helm \
      /usr/local/bin/helm
    # Install Docker
    sudo sh $(get_extra_file https://get.docker.com)
    sudo usermod -aG docker $USER
    sudo iptables -I DOCKER-USER -j ACCEPT
    # Create a KinD cluster
    ensure_kind_cluster
    # Install ORC
    kubectl apply -f "https://github.com/k-orc/openstack-resource-controller/releases/download/${ORC_VERSION}/install.yaml"
    # Deploy CAPI/CAPO and the CSR approver
    CLUSTERCTL_CONFIG=$(mktemp --suffix=.yaml)
    write_clusterctl_config ${CLUSTERCTL_CONFIG}
    export EXP_CLUSTER_RESOURCE_SET=true
    export EXP_KUBEADM_BOOTSTRAP_FORMAT_IGNITION=true
    export CLUSTER_TOPOLOGY=true
    clusterctl init \
      --config ${CLUSTERCTL_CONFIG} \
      --core cluster-api:${CAPI_VERSION} \
      --bootstrap kubeadm:${CAPI_VERSION} \
      --control-plane kubeadm:${CAPI_VERSION} \
      --infrastructure openstack:${CAPO_VERSION} \
      --addon csr-approver:${CSR_APPROVER_VERSION}
    # Wait for components to go up
    kubectl -n capi-kubeadm-bootstrap-system rollout status deploy/capi-kubeadm-bootstrap-controller-manager
    kubectl -n capi-kubeadm-control-plane-system rollout status deploy/capi-kubeadm-control-plane-controller-manager
    kubectl -n capi-system rollout status deploy/capi-controller-manager
    kubectl -n capo-system rollout status deploy/capo-controller-manager
    kubectl -n capi-csr-approver-system rollout status deploy/capi-csr-approver-controller-manager
    :

  elif [[ "$1" == "stack" && "$2" == "install" ]]; then
    git_clone $MAGNUM_CLUSTER_API_REPO $MAGNUM_CLUSTER_API_DIR $MAGNUM_CLUSTER_API_DIR
    setup_develop $MAGNUM_CLUSTER_API_DIR

  elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
    # Configure
    :

  elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
    # Initialize
    :
  fi

  if [[ "$1" == "unstack" ]]; then
    # Shut down template services
    # no-op
    :
  fi

  if [[ "$1" == "clean" ]]; then
    # Remove state and transient data
    # Remember clean.sh first calls unstack.sh
    # no-op
    :
  fi
fi
