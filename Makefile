clean:
	rm -rfv magnum_cluster_api/charts/cluster-autoscaler

vendor: clean
	helm repo add autoscaler https://kubernetes.github.io/autoscaler
	helm repo update
	helm fetch autoscaler/cluster-autoscaler --version 9.29.1 --untar --untardir magnum_cluster_api/charts
	patch -p0 magnum_cluster_api/charts/cluster-autoscaler/templates/clusterrole.yaml < hack/add-omt-to-clusterrole.patch

maturin:
	pipx install maturin

build: vendor maturin
	maturin build
