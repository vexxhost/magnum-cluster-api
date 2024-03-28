clean:
	rm -rfv magnum_cluster_api/charts/vendor

vendir:
	curl -Lo vendir https://github.com/carvel-dev/vendir/releases/download/v0.40.0/vendir-linux-amd64
	chmod +x vendir && ./vendir version
	mv vendir /usr/local/bin/vendir

vendor: clean vendir
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
