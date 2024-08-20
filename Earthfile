VERSION 0.7

build:
  FROM github.com/vexxhost/atmosphere/images/magnum+build
  COPY github.com/vexxhost/atmosphere/images/helm+binary/helm /usr/local/bin/helm
  COPY --dir magnum_cluster_api/ pyproject.toml README.md /src
  WORKDIR /src
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
