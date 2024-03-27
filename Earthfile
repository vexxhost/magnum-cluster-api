VERSION 0.7

vendir:
  FROM github.com/vexxhost/atmosphere/images/curl+image
  ARG TARGETOS
  ARG TARGETARCH
  ARG VERSION=v0.40.0
  RUN curl -Lo vendir https://github.com/carvel-dev/vendir/releases/download/${VERSION}/vendir-${TARGETOS}-${TARGETARCH}
  RUN chmod +x vendir && ./vendir version
  SAVE ARTIFACT vendir

build:
  FROM github.com/vexxhost/atmosphere/images/magnum+build
  COPY +vendir/vendir /usr/local/bin/vendir
  COPY github.com/vexxhost/atmosphere/images/helm+binary/helm /usr/local/bin/helm
  COPY --dir magnum_cluster_api/ pyproject.toml README.md vendir.yml /src
  WORKDIR /src
	RUN vendir sync
  COPY hack/add-omt-to-clusterrole.patch /hack/
	RUN patch -p0 magnum_cluster_api/charts/vendor/cluster-autoscaler/templates/clusterrole.yaml < /hack/add-omt-to-clusterrole.patch
  DO github.com/vexxhost/atmosphere/images/openstack-service+PIP_INSTALL --PACKAGES /src
  SAVE ARTIFACT /var/lib/openstack venv

image:
  FROM github.com/vexxhost/atmosphere/images/openstack-service+image --PROJECT magnum --RELEASE 2023.2
  DO github.com/vexxhost/atmosphere/images+APT_INSTALL --PACKAGES "haproxy"
  COPY github.com/vexxhost/atmosphere/images/helm+binary/helm /usr/local/bin/helm
  COPY +build/venv /var/lib/openstack
  ARG --required GIT_SHA
  SAVE IMAGE --push quay.io/vexxhost/magnum-cluster-api:${GIT_SHA}

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
