VERSION 0.7

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
  RUN --push mkdocs gh-deploy
