KIND_VERSION=${KIND_VERSION:-v0.16.0}
MAGNUM_CLUSTER_API_REPO=${MAGNUM_CLUSTER_API_REPO:-https://github.com/vexxhost/magnum-cluster-api.git}
MAGNUM_CLUSTER_API_BRANCH=${MAGNUM_CLUSTER_API_BRANCH:-main}
MAGNUM_CLUSTER_API_DIR=$DEST/magnum-cluster-api

if is_service_enabled magnum-cluster-api; then

  if [[ "$1" == "stack" && "$2" == "pre-install" ]]; then
    # Install Kubectl
    local kubectl_bin=$(get_extra_file https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl)
    sudo install -o root -g root -m 0755 ${kubectl_bin} /usr/local/bin/kubectl
    # Install Docker
    local get_docker=$(get_extra_file https://get.docker.com)
    sudo sh ${get_docker}
    sudo usermod -aG docker $USER
    sudo iptables -I DOCKER-USER -j ACCEPT
    # Install KinD
    local kind_bin=$(get_extra_file https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64)
    sudo install -o root -g root -m 0755 ${kind_bin} /usr/local/bin/kind
    # Create a KinD cluster
    echo "kind create cluster" | newgrp docker
    # Label a control plane node
    kubectl label node kind-control-plane openstack-control-plane=enabled
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
