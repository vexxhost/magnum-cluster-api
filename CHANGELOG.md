# Changelog

## [0.7.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.7.0...v0.7.1) (2023-06-30)


### Bug Fixes

* Do not upgrade helmrelease in pending status ([81bb06c](https://github.com/vexxhost/magnum-cluster-api/commit/81bb06c054d4c7fa2f199171be6d58b2a5e16cf4))

## [0.7.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.6.0...v0.7.0) (2023-06-29)


### Features

* Allow odd number of master count only ([c6488c7](https://github.com/vexxhost/magnum-cluster-api/commit/c6488c7c3cb0bf494d705b487d74bc76bb1ccdf0))
* Expose underlying k8s resource status to coe cluster status reason ([cd0438a](https://github.com/vexxhost/magnum-cluster-api/commit/cd0438a30331383771d8e687408130ce33d54610))
* Support OpenID Connect for kube-api auth ([0a33863](https://github.com/vexxhost/magnum-cluster-api/commit/0a338631793ec8ae6494a5453b5c332ad9ff0094))


### Bug Fixes

* Fix the certificate deletion ([17c243a](https://github.com/vexxhost/magnum-cluster-api/commit/17c243a906cdbf14e8fe74f60f3f5f8166eb3c82))
* Set the cluster status as in_progress at the end of update_nodegroup handler ([9d3312c](https://github.com/vexxhost/magnum-cluster-api/commit/9d3312c3e542b5764b8643453cd0efa052efd082))
* Skip delete_cluster when stack_id is none ([cabd872](https://github.com/vexxhost/magnum-cluster-api/commit/cabd8729b64d8a716f8b970a1d91234c279a03b4)), closes [#126](https://github.com/vexxhost/magnum-cluster-api/issues/126)
* solve race condition for stack_id ([43474f1](https://github.com/vexxhost/magnum-cluster-api/commit/43474f1c81cc1268afdac4f4f21681ded28fcfa4))


### Documentation

* added basic troubleshooting docs ([f2f2983](https://github.com/vexxhost/magnum-cluster-api/commit/f2f2983c059334f18b94da272a99faa9efd2f46d))

## [0.6.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.5.4...v0.6.0) (2023-06-01)


### Features

* Add manila csi ([fceabed](https://github.com/vexxhost/magnum-cluster-api/commit/fceabedb2e8913b8bff858073f6eb532c4d93dc3))


### Bug Fixes

* return helm output ([95c32a7](https://github.com/vexxhost/magnum-cluster-api/commit/95c32a79bdb1630365b951176e1c6c9fbc50d93c))
* Wait until observedGeneration of the capi cluster is increased in cluster upgrade ([58b6325](https://github.com/vexxhost/magnum-cluster-api/commit/58b632569496961ac9ffb09c00e043627791bb6e)), closes [#57](https://github.com/vexxhost/magnum-cluster-api/issues/57)

## [0.5.4](https://github.com/vexxhost/magnum-cluster-api/compare/v0.5.3...v0.5.4) (2023-04-24)


### Bug Fixes

* remove deleted nodegroups ([66c650f](https://github.com/vexxhost/magnum-cluster-api/commit/66c650faf481058261e2befe917bfc1d289f8a39))
* stop adding cluster name to node name ([0024683](https://github.com/vexxhost/magnum-cluster-api/commit/002468379a0ffd8cc20490477e46ac43bacb6478)), closes [#96](https://github.com/vexxhost/magnum-cluster-api/issues/96)
* use api from arg ([386eead](https://github.com/vexxhost/magnum-cluster-api/commit/386eeadd6614cb30d108ba42fb3456da226d5f34))

## [0.5.3](https://github.com/vexxhost/magnum-cluster-api/compare/v0.5.2...v0.5.3) (2023-04-13)


### Bug Fixes

* add tests to validate rewriting manifests ([c8944da](https://github.com/vexxhost/magnum-cluster-api/commit/c8944dac31204a42ffc572f21b0c2581f71415a3))

## [0.5.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.5.1...v0.5.2) (2023-04-13)


### Bug Fixes

* test image loader ([7e7b30c](https://github.com/vexxhost/magnum-cluster-api/commit/7e7b30c57f8cd5ad16bf71d84fc6a2c99cb5e7c7))

## [0.5.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.5.0...v0.5.1) (2023-04-11)


### Bug Fixes

* avoid overriding api_address ([f7009cc](https://github.com/vexxhost/magnum-cluster-api/commit/f7009ccd36756cbd40c622538c2831d0bff3004c))
* clean-up old endpoint slices ([730743e](https://github.com/vexxhost/magnum-cluster-api/commit/730743efe4ecd1233033fd7fa8119076981e4d01))
* correct dependency list ([65e2ea1](https://github.com/vexxhost/magnum-cluster-api/commit/65e2ea1f5ff3e6ea8287b97f14af8111d84f5f4c))
* remove tracebacks for missing objects ([a148d4f](https://github.com/vexxhost/magnum-cluster-api/commit/a148d4f89744b01c6e29c4f1ecbd723230f6b21c)), closes [#68](https://github.com/vexxhost/magnum-cluster-api/issues/68)

## [0.5.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.4.2...v0.5.0) (2023-04-10)


### Features

* add m-capi-proxy ([a699349](https://github.com/vexxhost/magnum-cluster-api/commit/a699349f61d3db0d1d81fe5a94fd8b5fdaa6db12))

## [0.4.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.4.1...v0.4.2) (2023-04-04)


### Bug Fixes

* Add missing autoscaler chart manifests ([122f4b9](https://github.com/vexxhost/magnum-cluster-api/commit/122f4b9d9d417a13150b692149533e7b6c81f2db))

## [0.4.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.4.0...v0.4.1) (2023-04-04)


### Bug Fixes

* build generic wheels ([1f1273b](https://github.com/vexxhost/magnum-cluster-api/commit/1f1273b043402ae406965b7bddf7831ece6e715a))

## [0.4.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.3.4...v0.4.0) (2023-04-04)


### Features

* add cluster-autoscaler ([cf05ce5](https://github.com/vexxhost/magnum-cluster-api/commit/cf05ce5f463b0f32794ca7047b46eb48796486f3))
* Eliminate flux dependency for cluster autoscaler ([3276d9a](https://github.com/vexxhost/magnum-cluster-api/commit/3276d9ace559bfc585c211292f584a8cfdef8a08))


### Bug Fixes

* solve black conflict ([e17ca40](https://github.com/vexxhost/magnum-cluster-api/commit/e17ca4088f1abd4c5ee6b7ee481f2117fadf5057))

## [0.3.4](https://github.com/vexxhost/magnum-cluster-api/compare/v0.3.3...v0.3.4) (2023-03-27)


### Bug Fixes

* add containerd settings to workers ([ff708dd](https://github.com/vexxhost/magnum-cluster-api/commit/ff708dd6e110a8ef8fb2d40348dd6dad35e057ae))

## [0.3.3](https://github.com/vexxhost/magnum-cluster-api/compare/v0.3.2...v0.3.3) (2023-03-27)


### Bug Fixes

* addd 1.26.2 images ([119b2c6](https://github.com/vexxhost/magnum-cluster-api/commit/119b2c6fed91dc4ad82878007ed84f3bc77df6ad))
* name replacement for new repo ([0eaeeba](https://github.com/vexxhost/magnum-cluster-api/commit/0eaeeba06bf3161260cb139a5da45a4755dcb3f0))
* replace the repository name ([bda20a2](https://github.com/vexxhost/magnum-cluster-api/commit/bda20a23d1845f022091029e0ed10598e07c1a94))
* use 20.04 by default ([0af2de3](https://github.com/vexxhost/magnum-cluster-api/commit/0af2de3c5a4ce4600bcc28be944edef19a887dfd))
* use correct sandbox_image ([80d74d2](https://github.com/vexxhost/magnum-cluster-api/commit/80d74d26d5d341c0042a794a2f5ab7151952442c))
* use new registry + 1.26.2 images ([b6c814f](https://github.com/vexxhost/magnum-cluster-api/commit/b6c814f503b939ae48ed97a8b86f003f7b9346e1))


### Documentation

* remove broken 1.26.2 images ([42f8a5f](https://github.com/vexxhost/magnum-cluster-api/commit/42f8a5f9a5221b8b7609c9524c1a079ac919d6b8))

## [0.3.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.3.1...v0.3.2) (2023-02-17)


### Bug Fixes

* solve cinder-csi usage ([8e9157b](https://github.com/vexxhost/magnum-cluster-api/commit/8e9157b8974a02ed92cf41cd36d4014241f7083c))

## [0.3.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.3.0...v0.3.1) (2023-02-03)


### Bug Fixes

* allow for mirroring to insecure registry ([3d9e364](https://github.com/vexxhost/magnum-cluster-api/commit/3d9e3645360f0f098499d5437fccdd0adab418e8))

## [0.3.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.7...v0.3.0) (2023-02-01)


### Features

* Use crane for image loader instead of skopeo ([8567f90](https://github.com/vexxhost/magnum-cluster-api/commit/8567f90ad2affacb037e4326e6314106299fad24))


### Bug Fixes

* Add clusterctl installation in hack script ([66f36be](https://github.com/vexxhost/magnum-cluster-api/commit/66f36bef91c46e1141e841dcb3a3c579e5334d30))
* change "fixed_subnet_cidr" default value ([387fd99](https://github.com/vexxhost/magnum-cluster-api/commit/387fd995fa4d8fac95b07bc285843349a58dca6d))
* incorrect print command ([a555440](https://github.com/vexxhost/magnum-cluster-api/commit/a5554401fbd2844b5b09cd74d3491c856a9ddd2b))
* update repo for initContainers ([f66bb4b](https://github.com/vexxhost/magnum-cluster-api/commit/f66bb4b450736ef38656a1091c4a794d0b7f560f))


### Documentation

* added info where to install crane ([084d191](https://github.com/vexxhost/magnum-cluster-api/commit/084d191253a6050b202f1c080fa68b06c51ff100))

## [0.2.7](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.6...v0.2.7) (2023-01-16)


### Bug Fixes

* only add cluster uuid to labels ([76099d4](https://github.com/vexxhost/magnum-cluster-api/commit/76099d44d7c069a07a16e696fde8bec2076cb50d))

## [0.2.6](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.5...v0.2.6) (2022-12-14)


### Bug Fixes

* Fix tls-insecure of ccm configuration ([5c9ad68](https://github.com/vexxhost/magnum-cluster-api/commit/5c9ad68e4aa7ec9ba087bf4330ef9f805a15250e))

## [0.2.5](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.4...v0.2.5) (2022-12-13)


### Bug Fixes

* Use public auth_url for CloudConfigSecret ([4f9c852](https://github.com/vexxhost/magnum-cluster-api/commit/4f9c852597b2631ec1cf6cea6e5afbe86b68fb21))

## [0.2.4](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.3...v0.2.4) (2022-12-12)


### Bug Fixes

* use endpoint_type for nova ([688d844](https://github.com/vexxhost/magnum-cluster-api/commit/688d84408efcebd0dfcde6648b2db8c5a7cce1c9))

## [0.2.3](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.2...v0.2.3) (2022-12-12)


### Bug Fixes

* use nova_client interface ([5dc34f3](https://github.com/vexxhost/magnum-cluster-api/commit/5dc34f3e28c7e9246c6b35eebb232cddeda64a5e))

## [0.2.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.1...v0.2.2) (2022-12-12)


### Bug Fixes

* respect verify_ca and openstack_ca ([107cc2f](https://github.com/vexxhost/magnum-cluster-api/commit/107cc2f302ddf41dfa4080cd6034a93639184f59))

## [0.2.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.2.0...v0.2.1) (2022-12-10)


### Bug Fixes

* enable ssl access ([7251c8a](https://github.com/vexxhost/magnum-cluster-api/commit/7251c8a240a90dcc1dac3abd28450aca591a3684))

## [0.2.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.1.2...v0.2.0) (2022-11-16)


### Bug Fixes

* added flux + node labels ([5f04d4e](https://github.com/vexxhost/magnum-cluster-api/commit/5f04d4ed8b00ba0d45cc59edd678bdf72679b00b))


### Miscellaneous Chores

* release 0.2.0 ([9c8fe82](https://github.com/vexxhost/magnum-cluster-api/commit/9c8fe8252e61b43019a0c45d31284467ec99af15))

## [0.1.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.1.1...v0.1.2) (2022-11-10)

### Bug Fixes

* disable profiling ([d18936e](https://github.com/vexxhost/magnum-cluster-api/commit/d18936e9ae76c996c6b4ff8ecbadcf666da572b0)), closes [#30](https://github.com/vexxhost/magnum-cluster-api/issues/30) [#35](https://github.com/vexxhost/magnum-cluster-api/issues/35) [#36](https://github.com/vexxhost/magnum-cluster-api/issues/36)
* relax pykube-ng requirement ([10be62a](https://github.com/vexxhost/magnum-cluster-api/commit/10be62a3786312845cd6959db4a3e00eb4073da4))

## [0.1.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.1.0...v0.1.1) (2022-11-10)

### Bug Fixes

* support py3.6+ ([4e1e0b5](https://github.com/vexxhost/magnum-cluster-api/commit/4e1e0b58c264632a1af7ae198c1d1b768330f38f))

## 0.1.0 (2022-11-10)

### Features

* add auto healing ([402b23b](https://github.com/vexxhost/magnum-cluster-api/commit/402b23b1999bc7388a58cc20e0e903656e663bec))
* add image builds ([2d5248b](https://github.com/vexxhost/magnum-cluster-api/commit/2d5248b8153bf4dd32a51436109d30c3a2bf6922))
* add imageRepository for container images ([ccd2f6a](https://github.com/vexxhost/magnum-cluster-api/commit/ccd2f6a5042f0ec1807bbf8534d32abff2286dfc))
* add magnum certs ([19cccb6](https://github.com/vexxhost/magnum-cluster-api/commit/19cccb62c7a37ea771fb54548a99070258f6f85c))
* add tool to load image repository ([56c7ca9](https://github.com/vexxhost/magnum-cluster-api/commit/56c7ca99b40a8ef30172f1f71bd8046ed34b9845))
* added cluster resize ([fa1e300](https://github.com/vexxhost/magnum-cluster-api/commit/fa1e3008952813a9129db4fa69e55dde553a9cee))
* added csi support ([c9a2374](https://github.com/vexxhost/magnum-cluster-api/commit/c9a2374b7337bf8b68bf9ec4fe94584eb330dab9))
* added ng + create_complete ([b805ad5](https://github.com/vexxhost/magnum-cluster-api/commit/b805ad53904df04d7f4c95a23b8092b367ef1e11))
* allow using `container_infra_prefix` ([5676b70](https://github.com/vexxhost/magnum-cluster-api/commit/5676b70cf5ad9614c8332ba5587b0075a90ee9f8)), closes [#7](https://github.com/vexxhost/magnum-cluster-api/issues/7)
* refactor to clusterclass ([a021300](https://github.com/vexxhost/magnum-cluster-api/commit/a0213005630e9edbc23c5c7c168ead062c92c926))
* use shorter cluster names ([7b58739](https://github.com/vexxhost/magnum-cluster-api/commit/7b58739c5262f6b5f28533a722ac8ec10ebf6c6a))

### Bug Fixes

* add context to openstackmachinetemplate ([6ff86b1](https://github.com/vexxhost/magnum-cluster-api/commit/6ff86b1fcd5ddd621c9f771fefce2a861eb65768))
* added update_cluster_status ([faa153b](https://github.com/vexxhost/magnum-cluster-api/commit/faa153b17a5467436d9fa2fb76744bfc7a642a76))
* allow cluster deletion ([7dc615f](https://github.com/vexxhost/magnum-cluster-api/commit/7dc615f1725b6a5235c95a173adab2253dc8927f))
* allow for optional ssh key ([c2ed0af](https://github.com/vexxhost/magnum-cluster-api/commit/c2ed0af9a773c75ada9db978088aab8818c2593a))
* allow glance to use 10G images ([f222cb1](https://github.com/vexxhost/magnum-cluster-api/commit/f222cb121b2b81660cdc174707d40c7882fc050a))
* clean-up cluster on failures ([b2f0d9e](https://github.com/vexxhost/magnum-cluster-api/commit/b2f0d9eb0df0ccdb28d0431005b77b4c6a806634))
* cluster creation ([62b89f0](https://github.com/vexxhost/magnum-cluster-api/commit/62b89f0561d1ab0d14086a85181aabbed71380ac))
* CREATE_COMPLETE state ([898c818](https://github.com/vexxhost/magnum-cluster-api/commit/898c818f354394d5ff898c2f911fa0f88b6771f1))
* first pass at upgrades ([28ce8b0](https://github.com/vexxhost/magnum-cluster-api/commit/28ce8b0fddc2ea4447dbedc7db1df9763a823794))
* image builds ([434f57d](https://github.com/vexxhost/magnum-cluster-api/commit/434f57da1cd5f7e2a9e29c770acdde57678b0fd7))
* move mhc to clusterclass ([c43ae93](https://github.com/vexxhost/magnum-cluster-api/commit/c43ae930db7d7e13cedfd8dd80b1ede0fd0dc4a4))
* pre-delete lbs ([513d0ff](https://github.com/vexxhost/magnum-cluster-api/commit/513d0ff5118f33ab025e512001f71baf3e1675c9)), closes [#6](https://github.com/vexxhost/magnum-cluster-api/issues/6)
* reconcile ng status ([1221e94](https://github.com/vexxhost/magnum-cluster-api/commit/1221e94e71cc88fa70839004c705af37e80ae99f))
* remove completed todo ([0d4bf03](https://github.com/vexxhost/magnum-cluster-api/commit/0d4bf034195a72276a17a05853bef85b37a52a00))
* resolve resize_cluster ([7efa4f9](https://github.com/vexxhost/magnum-cluster-api/commit/7efa4f92cbe2b1b73cbe50417113b9fb0b108ae5))
* stop docker from tinkering ([6fdf1d2](https://github.com/vexxhost/magnum-cluster-api/commit/6fdf1d2312d66f7e087c74ea74b9ad0be3d874cc))
* upgrades ([bda670d](https://github.com/vexxhost/magnum-cluster-api/commit/bda670d25ae78f1d1e3e3afafd17ccaaebc959cf))
* use dynamic `ClusterClass` version ([d7fbbf0](https://github.com/vexxhost/magnum-cluster-api/commit/d7fbbf0665178028a79d2f184adcf1f55e68dcd4)), closes [#16](https://github.com/vexxhost/magnum-cluster-api/issues/16)
* use getpass.getuser ([67e1ec5](https://github.com/vexxhost/magnum-cluster-api/commit/67e1ec5b70f5b2ebbcb5b773b6a09cb249cfd0f9))
* use operating_system ([062e7f3](https://github.com/vexxhost/magnum-cluster-api/commit/062e7f3390ccf3fecc26c045f6eaed2adb9619a4))

### Documentation

* add devstack docs ([3dc6c69](https://github.com/vexxhost/magnum-cluster-api/commit/3dc6c6997ab29147d9185fd860c4345017a51719))
* added devstack info ([e8059d9](https://github.com/vexxhost/magnum-cluster-api/commit/e8059d9d6651dbdb9dbbccfa2ac961e957212144))
* fix typos ([27b94c3](https://github.com/vexxhost/magnum-cluster-api/commit/27b94c3b80e822cb605513fb85d7d7df21f33817))
* update adding images ([d90ba3c](https://github.com/vexxhost/magnum-cluster-api/commit/d90ba3c53571dfa382e3d044c2dd5ce2c1d759ed))
