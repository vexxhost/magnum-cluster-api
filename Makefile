clean:
	rm -rfv magnum_cluster_api/charts/cluster-autoscaler

vendor: clean
	helm repo add autoscaler https://kubernetes.github.io/autoscaler
	helm repo update
	helm fetch autoscaler/cluster-autoscaler --version 9.27.0 --untar --untardir magnum_cluster_api/charts
	patch -p0 magnum_cluster_api/charts/cluster-autoscaler/templates/clusterrole.yaml < hack/add-omt-to-clusterrole.patch

build: vendor
	poetry build

install: build
	poetry install

test: install
	poetry run pytest
