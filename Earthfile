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
