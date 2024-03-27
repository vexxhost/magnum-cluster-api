clean:
	rm -rfv magnum_cluster_api/charts/cluster-autoscaler

vendor: clean
	vendir sync
	patch -p0 magnum_cluster_api/charts/vendor/cluster-autoscaler/templates/clusterrole.yaml < hack/add-omt-to-clusterrole.patch

poetry:
	pipx install poetry

build: vendor poetry
	poetry build

install: build poetry
	poetry install

unit-tests: install poetry
	poetry run pytest magnum_cluster_api/tests/unit/

functional-tests: install poetry
	poetry run pytest magnum_cluster_api/tests/functional/
