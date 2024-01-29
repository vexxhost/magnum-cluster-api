VERSION 0.7

build:
  FROM github.com/vexxhost/atmosphere/images/magnum+build
  COPY github.com/vexxhost/atmosphere/images/helm+binary/helm /usr/local/bin/helm
	RUN helm repo add autoscaler https://kubernetes.github.io/autoscaler
	RUN helm repo update
  COPY --dir magnum_cluster_api/ pyproject.toml README.md /src
  WORKDIR /src
	RUN helm fetch autoscaler/cluster-autoscaler --version 9.29.1 --untar --untardir magnum_cluster_api/charts
  COPY hack/add-omt-to-clusterrole.patch /hack/
	RUN patch -p0 magnum_cluster_api/charts/cluster-autoscaler/templates/clusterrole.yaml < /hack/add-omt-to-clusterrole.patch
  DO github.com/vexxhost/atmosphere/images/openstack-service+PIP_INSTALL --PACKAGES /src

image:
  FROM github.com/vexxhost/atmosphere/images/openstack-service+image --PROJECT magnum --RELEASE 2023.2
  DO github.com/vexxhost/atmosphere/images+APT_INSTALL --PACKAGES "haproxy"
  COPY github.com/vexxhost/atmosphere/images/helm+binary/helm /usr/local/bin/helm
  COPY +build/venv /var/lib/openstack
  ARG --required GIT_SHA
  SAVE ARTIFACT quay.io/vexxhost/magnum-cluster-api:${GIT_SHA}

mkdocs-image:
  FROM squidfunk/mkdocs-material:9.1.15
  RUN pip install \
    mkdocs-literate-nav
  SAVE IMAGE mkdocs

mkdocs-serve:
  LOCALLY
  WITH DOCKER --load=+mkdocs-image
    RUN docker run --rm -p 8000:8000 -v ${PWD}:/docs mkdocs
  END

mkdocs-build:
  FROM +mkdocs-image
  COPY . /docs
  RUN mkdocs build
  RUN --push --secret GITHUB_TOKEN git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/vexxhost/magnum-cluster-api.git
  RUN --push mkdocs gh-deploy --force
