clean-chart-%:
	rm -rfv magnum_cluster_api/charts/$*

helm-repo-autoscaler:
	helm repo add autoscaler https://kubernetes.github.io/autoscaler
	helm repo update

vendor-cluster-autoscaler: clean-chart-cluster-autoscaler helm-repo-autoscaler
	helm fetch autoscaler/cluster-autoscaler --version 9.27.0 --untar --untardir magnum_cluster_api/charts
	patch -p0 magnum_cluster_api/charts/cluster-autoscaler/templates/clusterrole.yaml < hack/add-omt-to-clusterrole.patch

helm-repo-cpo:
	helm repo add cpo https://kubernetes.github.io/cloud-provider-openstack
	helm repo update

vendor-cpo-%: clean-chart-$* helm-repo-cpo
	helm fetch cpo/$* --version 2.27.1 --untar --untardir magnum_cluster_api/charts

vendor-openstack-cloud-controller-manager: clean-chart-openstack-cloud-controller-manager helm-repo-cpo
	helm fetch cpo/openstack-cloud-controller-manager --version 2.27.1 --untar --untardir magnum_cluster_api/charts

vendor-openstack-cinder-csi: clean-chart-openstack-cinder-csi helm-repo-cpo
	helm fetch cpo/openstack-cinder-csi --version 2.27.1 --untar --untardir magnum_cluster_api/charts

vendor-openstack-manila-csi: clean-chart-openstack-manila-csi helm-repo-cpo
	helm fetch cpo/openstack-manila-csi --version 2.27.1 --untar --untardir magnum_cluster_api/charts

.PHONY: vendor
vendor: vendor-cluster-autoscaler vendor-openstack-cloud-controller-manager vendor-openstack-cinder-csi vendor-openstack-manila-csi

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
