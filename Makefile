clean:
	rm -rfv magnum_cluster_api/charts/cluster-autoscaler

vendor: clean
	helm repo add autoscaler https://kubernetes.github.io/autoscaler
	helm repo update
	helm fetch autoscaler/cluster-autoscaler --version 9.27.0 --untar --untardir magnum_cluster_api/charts
	patch -p0 magnum_cluster_api/charts/cluster-autoscaler/templates/clusterrole.yaml < hack/add-omt-to-clusterrole.patch

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
