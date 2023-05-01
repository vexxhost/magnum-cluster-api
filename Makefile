clean-cluster-autoscaler:
	rm -rfv magnum_cluster_api/charts/cluster-autoscaler

vendor-cluster-autoscaler: clean-cluster-autoscaler
	helm repo add autoscaler https://kubernetes.github.io/autoscaler
	helm repo update
	helm fetch autoscaler/cluster-autoscaler --version 9.27.0 --untar --untardir magnum_cluster_api/charts
	patch -p0 magnum_cluster_api/charts/cluster-autoscaler/templates/clusterrole.yaml < hack/add-omt-to-clusterrole.patch

clean-openstack-cloud-controller-manager:
	rm -rfv magnum_cluster_api/charts/openstack-cloud-controller-manager

vendor-openstack-cloud-controller-manager: clean-openstack-cloud-controller-manager
	helm repo add cpo https://kubernetes.github.io/cloud-provider-openstack
	helm repo update
	helm fetch cpo/openstack-cloud-controller-manager --version 2.27.1 --untar --untardir magnum_cluster_api/charts

.PHONY: vendor
vendor: vendor-cluster-autoscaler vendor-openstack-cloud-controller-manager

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
