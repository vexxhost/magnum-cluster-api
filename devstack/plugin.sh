MAGNUM_CLUSTER_API_REPO=${MAGNUM_REPO:-https://github.com/vexxhost/magnum-cluster-api.git}
MAGNUM_CLUSTER_API_BRANCH=${MAGNUM_BRANCH:-main}
MAGNUM_CLUSTER_API_DIR=$DEST/magnum-cluster-api

if is_service_enabled magnum-cluster-api; then

  if [[ "$1" == "stack" && "$2" == "pre-install" ]]; then
    # Pre-install packages
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
