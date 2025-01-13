# Changelog

## [0.24.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.24.1...v0.24.2) (2025-01-13)


### Miscellaneous Chores

* release 0.24.2 ([36f95a2](https://github.com/vexxhost/magnum-cluster-api/commit/36f95a2142792fb262eb99f66df5c5d4cc0ede12))

## [0.24.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.24.0...v0.24.1) (2025-01-11)


### Miscellaneous Chores

* release 0.24.1 ([cfb4f64](https://github.com/vexxhost/magnum-cluster-api/commit/cfb4f6443cbf5918389268cfb6dd6f125a458505))

## [0.24.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.23.0...v0.24.0) (2024-11-26)


### Miscellaneous Chores

* release 0.24.0 ([6766b02](https://github.com/vexxhost/magnum-cluster-api/commit/6766b02ebfb98d18cb523ab5921673f7bc43370a))

## [0.23.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.22.1...v0.23.0) (2024-10-21)


### Miscellaneous Chores

* release 0.23.0 ([8110c75](https://github.com/vexxhost/magnum-cluster-api/commit/8110c753e42d66baa353b3e31738bb71dd0dded2))

## [0.22.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.22.0...v0.22.1) (2024-09-06)


### Bug Fixes

* include nodegroups in COMPLETE status in cluster update job ([#427](https://github.com/vexxhost/magnum-cluster-api/issues/427)) ([b50b6dc](https://github.com/vexxhost/magnum-cluster-api/commit/b50b6dc83a8f49f01aacf6fec99b670c1316a620))

## [0.22.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.21.2...v0.22.0) (2024-08-07)


### Features

* update handling vendor charts and add linters ([#413](https://github.com/vexxhost/magnum-cluster-api/issues/413)) ([141d536](https://github.com/vexxhost/magnum-cluster-api/commit/141d5361db0b90542bf3c0d8e9dd777833711253))

## [0.21.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.21.1...v0.21.2) (2024-07-19)


### Bug Fixes

* allow skipping node groups that are master or delete complete ([#415](https://github.com/vexxhost/magnum-cluster-api/issues/415)) ([bd32dec](https://github.com/vexxhost/magnum-cluster-api/commit/bd32dec463b0990175ba4517b4539ceb9cc75f18))

## [0.21.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.21.0...v0.21.1) (2024-07-17)


### Bug Fixes

* add skips + breakout for DELETE_COMPLETE ([0e904b6](https://github.com/vexxhost/magnum-cluster-api/commit/0e904b6e256f6cfb5ddf32816707368ea6738ac2))


### Miscellaneous Chores

* release 0.21.1 ([8a16cf9](https://github.com/vexxhost/magnum-cluster-api/commit/8a16cf9330a075025d726c670746ae604a0c3a60))

## [0.21.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.20.0...v0.21.0) (2024-06-28)


### Miscellaneous Chores

* release 0.21.0 ([7906dfa](https://github.com/vexxhost/magnum-cluster-api/commit/7906dfab149fb58f7abed60701f1838d93caeeff))

## [0.20.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.19.2...v0.20.0) (2024-06-27)


### Features

* support additional cert sans [ATMOSPHERE-260] ([#402](https://github.com/vexxhost/magnum-cluster-api/issues/402)) ([da93f6a](https://github.com/vexxhost/magnum-cluster-api/commit/da93f6abc822579d52d88eace644c7d9bd0a8cdd))
* support cilium cni ([#287](https://github.com/vexxhost/magnum-cluster-api/issues/287)) ([4f922d0](https://github.com/vexxhost/magnum-cluster-api/commit/4f922d0a805cea8a4b0e6e520b28d81a55b5e150))

## [0.19.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.19.1...v0.19.2) (2024-06-20)


### Bug Fixes

* Add missing equal sign for mounts ([#397](https://github.com/vexxhost/magnum-cluster-api/issues/397)) ([2385424](https://github.com/vexxhost/magnum-cluster-api/commit/2385424421808083597ae282402368ece4957459))

## [0.19.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.19.0...v0.19.1) (2024-06-14)


### Bug Fixes

* Stop waiting on CAPI in API ([#393](https://github.com/vexxhost/magnum-cluster-api/issues/393)) ([024a3d9](https://github.com/vexxhost/magnum-cluster-api/commit/024a3d93cc3689d1cea7281dad3270be8b4d22c5))

## [0.19.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.18.0...v0.19.0) (2024-06-12)


### Features

* support docker volume type and size ([#370](https://github.com/vexxhost/magnum-cluster-api/issues/370)) ([5360349](https://github.com/vexxhost/magnum-cluster-api/commit/5360349333aa52b934b8f5cc37df859064dfed48))


### Bug Fixes

* Improve node group tracking ([#388](https://github.com/vexxhost/magnum-cluster-api/issues/388)) ([a0fbfdd](https://github.com/vexxhost/magnum-cluster-api/commit/a0fbfddfadadad736232713331665737f468e9b9))

## [0.18.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.17.1...v0.18.0) (2024-05-30)


### Features

* Update bind address for k8s components ([#197](https://github.com/vexxhost/magnum-cluster-api/issues/197)) ([4b1f5d8](https://github.com/vexxhost/magnum-cluster-api/commit/4b1f5d840fb9f2158e7c7d8ebca6f1a86fb8569f))


### Bug Fixes

* force a cluster upgrade all the time ([#382](https://github.com/vexxhost/magnum-cluster-api/issues/382)) ([436bcf2](https://github.com/vexxhost/magnum-cluster-api/commit/436bcf26eb3fb30efef67b01a8ad400ca1bcce03))

## [0.17.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.17.0...v0.17.1) (2024-05-28)


### Bug Fixes

* use get method to get obj component ([#376](https://github.com/vexxhost/magnum-cluster-api/issues/376)) ([c259a71](https://github.com/vexxhost/magnum-cluster-api/commit/c259a7142cdc90d68b453d286f1cc504722c3ee3)), closes [#368](https://github.com/vexxhost/magnum-cluster-api/issues/368)

## [0.17.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.16.0...v0.17.0) (2024-05-02)


### Features

* Automatically rotating certificates using Kubeadm Control Plane provider ([#361](https://github.com/vexxhost/magnum-cluster-api/issues/361)) ([9e4bed1](https://github.com/vexxhost/magnum-cluster-api/commit/9e4bed1d328e29cfaf43635978f6da4688768856))
* enable octavia_lb_algorithm label ([#358](https://github.com/vexxhost/magnum-cluster-api/issues/358)) ([bd339ee](https://github.com/vexxhost/magnum-cluster-api/commit/bd339eefa43f88e91281c7c3a132ed8c7bd313e2)), closes [#355](https://github.com/vexxhost/magnum-cluster-api/issues/355)
* support multiple control plane availability zones ([#320](https://github.com/vexxhost/magnum-cluster-api/issues/320)) ([8ceb19a](https://github.com/vexxhost/magnum-cluster-api/commit/8ceb19accf272c708bc09ed3340aa45c9ac54253))


### Bug Fixes

* fix unit tests for sync and disable image build job in CI ([#367](https://github.com/vexxhost/magnum-cluster-api/issues/367)) ([668d4f9](https://github.com/vexxhost/magnum-cluster-api/commit/668d4f9a62e5370408199b759eb8a7526ce06082))
* **ovn:** use octavia_provider for api lb ([#360](https://github.com/vexxhost/magnum-cluster-api/issues/360)) ([9b0ec1e](https://github.com/vexxhost/magnum-cluster-api/commit/9b0ec1eecd9a1ae067b4c046bb92c569d9c4d121))

## [0.16.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.15.1...v0.16.0) (2024-03-28)


### Features

* allow ovn lbs ([#348](https://github.com/vexxhost/magnum-cluster-api/issues/348)) ([80efca9](https://github.com/vexxhost/magnum-cluster-api/commit/80efca982ca979ee947bcc84ff37407f986a30d3))


### Bug Fixes

* solve lock issues + extra unit tests ([#343](https://github.com/vexxhost/magnum-cluster-api/issues/343)) ([3438204](https://github.com/vexxhost/magnum-cluster-api/commit/3438204a0787c5c84c1d6d5d496d8949ca73c2d5))
* **upgrades:** set correct cluster_template_id ([#349](https://github.com/vexxhost/magnum-cluster-api/issues/349)) ([49dc0c9](https://github.com/vexxhost/magnum-cluster-api/commit/49dc0c980d1f0c84032ab1f3517f0081afc76a38))

## [0.15.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.15.1...v0.15.1) (2024-03-22)


### Features

* add 1.27 support ([c256e74](https://github.com/vexxhost/magnum-cluster-api/commit/c256e74c4f76153b30fdaee68b92750a2e140d2f))
* add auto healing ([402b23b](https://github.com/vexxhost/magnum-cluster-api/commit/402b23b1999bc7388a58cc20e0e903656e663bec))
* add cluster-autoscaler ([cf05ce5](https://github.com/vexxhost/magnum-cluster-api/commit/cf05ce5f463b0f32794ca7047b46eb48796486f3))
* add image builds ([2d5248b](https://github.com/vexxhost/magnum-cluster-api/commit/2d5248b8153bf4dd32a51436109d30c3a2bf6922))
* add imageRepository for container images ([ccd2f6a](https://github.com/vexxhost/magnum-cluster-api/commit/ccd2f6a5042f0ec1807bbf8534d32abff2286dfc))
* Add labels for nodegroup name and role name ([bfc2f52](https://github.com/vexxhost/magnum-cluster-api/commit/bfc2f5228bdc6e137918c8ee721b20a689d24f95))
* add m-capi-proxy ([a699349](https://github.com/vexxhost/magnum-cluster-api/commit/a699349f61d3db0d1d81fe5a94fd8b5fdaa6db12))
* add magnum certs ([19cccb6](https://github.com/vexxhost/magnum-cluster-api/commit/19cccb62c7a37ea771fb54548a99070258f6f85c))
* Add manila csi ([fceabed](https://github.com/vexxhost/magnum-cluster-api/commit/fceabedb2e8913b8bff858073f6eb532c4d93dc3))
* add tool to load image repository ([56c7ca9](https://github.com/vexxhost/magnum-cluster-api/commit/56c7ca99b40a8ef30172f1f71bd8046ed34b9845))
* added cluster resize ([fa1e300](https://github.com/vexxhost/magnum-cluster-api/commit/fa1e3008952813a9129db4fa69e55dde553a9cee))
* added csi support ([c9a2374](https://github.com/vexxhost/magnum-cluster-api/commit/c9a2374b7337bf8b68bf9ec4fe94584eb330dab9))
* added ng + create_complete ([b805ad5](https://github.com/vexxhost/magnum-cluster-api/commit/b805ad53904df04d7f4c95a23b8092b367ef1e11))
* Allow odd number of master count only ([c6488c7](https://github.com/vexxhost/magnum-cluster-api/commit/c6488c7c3cb0bf494d705b487d74bc76bb1ccdf0))
* allow using `container_infra_prefix` ([5676b70](https://github.com/vexxhost/magnum-cluster-api/commit/5676b70cf5ad9614c8332ba5587b0075a90ee9f8)), closes [#7](https://github.com/vexxhost/magnum-cluster-api/issues/7)
* Eliminate flux dependency for cluster autoscaler ([3276d9a](https://github.com/vexxhost/magnum-cluster-api/commit/3276d9ace559bfc585c211292f584a8cfdef8a08))
* enable in-cluster traffic ([61bf7aa](https://github.com/vexxhost/magnum-cluster-api/commit/61bf7aa3bf1990eb0c067d4272b28305ea8eb155))
* Expose underlying k8s resource status to coe cluster status reason ([cd0438a](https://github.com/vexxhost/magnum-cluster-api/commit/cd0438a30331383771d8e687408130ce33d54610))
* Fetch node count from md object when autoscaling enabled ([d64ca86](https://github.com/vexxhost/magnum-cluster-api/commit/d64ca8637da2e181143f3156a07b0ca3abe10e97))
* refactor to clusterclass ([a021300](https://github.com/vexxhost/magnum-cluster-api/commit/a0213005630e9edbc23c5c7c168ead062c92c926))
* RockyLinux 8/9 support ([#326](https://github.com/vexxhost/magnum-cluster-api/issues/326)) ([2a53f3e](https://github.com/vexxhost/magnum-cluster-api/commit/2a53f3e340524deee3ddbf08b41071fba070d7d3))
* Support endpoint configuration for cluster-api ([#211](https://github.com/vexxhost/magnum-cluster-api/issues/211)) ([8a5ffac](https://github.com/vexxhost/magnum-cluster-api/commit/8a5ffac1e0ed3f1a7166dfd15a62b74f6a140963))
* support etcd volume ([#305](https://github.com/vexxhost/magnum-cluster-api/issues/305)) ([544cb77](https://github.com/vexxhost/magnum-cluster-api/commit/544cb77a4a2101dc2af6ee940ab05968f015fc1a))
* Support Flatcar OS ([#225](https://github.com/vexxhost/magnum-cluster-api/issues/225)) ([ef4401f](https://github.com/vexxhost/magnum-cluster-api/commit/ef4401f3019d04735c0ee85e4b8057896086c70a))
* support keystone-auth ([#297](https://github.com/vexxhost/magnum-cluster-api/issues/297)) ([50a2c27](https://github.com/vexxhost/magnum-cluster-api/commit/50a2c277be084fefcc7a53c9309716771c003ea8))
* Support OpenID Connect for kube-api auth ([0a33863](https://github.com/vexxhost/magnum-cluster-api/commit/0a338631793ec8ae6494a5453b5c332ad9ff0094))
* Support tls-cipher-suite configuration for kubelet ([5010c9a](https://github.com/vexxhost/magnum-cluster-api/commit/5010c9a4dd2c2656089b5807c38d95aec8c6ef0a))
* upgrade capi version ([#299](https://github.com/vexxhost/magnum-cluster-api/issues/299)) ([83535e7](https://github.com/vexxhost/magnum-cluster-api/commit/83535e7405e1a1ef1ce0251694eec78882873838))
* Use crane for image loader instead of skopeo ([8567f90](https://github.com/vexxhost/magnum-cluster-api/commit/8567f90ad2affacb037e4326e6314106299fad24))
* use shorter cluster names ([7b58739](https://github.com/vexxhost/magnum-cluster-api/commit/7b58739c5262f6b5f28533a722ac8ec10ebf6c6a))
* Validate fixed_network and fixed_subnet existence ([46ac9ac](https://github.com/vexxhost/magnum-cluster-api/commit/46ac9ac4ed288eac964af647d60d21d7865599c9))
* Validate flavors ([e438f4b](https://github.com/vexxhost/magnum-cluster-api/commit/e438f4b490b16b7f296e9828f1100067845cafae))


### Bug Fixes

* Add cacert in cloud config ([9fbdda6](https://github.com/vexxhost/magnum-cluster-api/commit/9fbdda6f0fa95ab48a0c25baa4ef26e1c1cbea96))
* Add clusterctl installation in hack script ([66f36be](https://github.com/vexxhost/magnum-cluster-api/commit/66f36bef91c46e1141e841dcb3a3c579e5334d30))
* add containerd settings to workers ([ff708dd](https://github.com/vexxhost/magnum-cluster-api/commit/ff708dd6e110a8ef8fb2d40348dd6dad35e057ae))
* add context to openstackmachinetemplate ([6ff86b1](https://github.com/vexxhost/magnum-cluster-api/commit/6ff86b1fcd5ddd621c9f771fefce2a861eb65768))
* add k8s-keystone-auth to image ([0c6ca67](https://github.com/vexxhost/magnum-cluster-api/commit/0c6ca67d5a98f0d404d9dd28b3bfb9e443c937be))
* Add missing autoscaler chart manifests ([122f4b9](https://github.com/vexxhost/magnum-cluster-api/commit/122f4b9d9d417a13150b692149533e7b6c81f2db))
* add tests to validate rewriting manifests ([c8944da](https://github.com/vexxhost/magnum-cluster-api/commit/c8944dac31204a42ffc572f21b0c2581f71415a3))
* add unit tests for image loader + missing images ([#268](https://github.com/vexxhost/magnum-cluster-api/issues/268)) ([5223b93](https://github.com/vexxhost/magnum-cluster-api/commit/5223b93c19e22b4e7d01a4d44bf0e720ca966832))
* addd 1.26.2 images ([119b2c6](https://github.com/vexxhost/magnum-cluster-api/commit/119b2c6fed91dc4ad82878007ed84f3bc77df6ad))
* added flux + node labels ([5f04d4e](https://github.com/vexxhost/magnum-cluster-api/commit/5f04d4ed8b00ba0d45cc59edd678bdf72679b00b))
* added update_cluster_status ([faa153b](https://github.com/vexxhost/magnum-cluster-api/commit/faa153b17a5467436d9fa2fb76744bfc7a642a76))
* address status changes for v1alpha7 ([5da7223](https://github.com/vexxhost/magnum-cluster-api/commit/5da72233baa3af3935f4624bd67894c68f5aa338))
* allow cluster deletion ([7dc615f](https://github.com/vexxhost/magnum-cluster-api/commit/7dc615f1725b6a5235c95a173adab2253dc8927f))
* allow configuring tls-cipher-suites ([#261](https://github.com/vexxhost/magnum-cluster-api/issues/261)) ([d1b7ab5](https://github.com/vexxhost/magnum-cluster-api/commit/d1b7ab5c2ea42eea35bfc87ede39ecd867ec94cf)), closes [#251](https://github.com/vexxhost/magnum-cluster-api/issues/251)
* allow for mirroring to insecure registry ([3d9e364](https://github.com/vexxhost/magnum-cluster-api/commit/3d9e3645360f0f098499d5437fccdd0adab418e8))
* allow for optional ssh key ([c2ed0af](https://github.com/vexxhost/magnum-cluster-api/commit/c2ed0af9a773c75ada9db978088aab8818c2593a))
* allow glance to use 10G images ([f222cb1](https://github.com/vexxhost/magnum-cluster-api/commit/f222cb121b2b81660cdc174707d40c7882fc050a))
* avoid overriding api_address ([f7009cc](https://github.com/vexxhost/magnum-cluster-api/commit/f7009ccd36756cbd40c622538c2831d0bff3004c))
* build generic wheels ([1f1273b](https://github.com/vexxhost/magnum-cluster-api/commit/1f1273b043402ae406965b7bddf7831ece6e715a))
* bump capi ([ba2866d](https://github.com/vexxhost/magnum-cluster-api/commit/ba2866defad25aac12f4055275251497311e4e22))
* change "fixed_subnet_cidr" default value ([387fd99](https://github.com/vexxhost/magnum-cluster-api/commit/387fd995fa4d8fac95b07bc285843349a58dca6d))
* clean-up cluster on failures ([b2f0d9e](https://github.com/vexxhost/magnum-cluster-api/commit/b2f0d9eb0df0ccdb28d0431005b77b4c6a806634))
* clean-up old endpoint slices ([730743e](https://github.com/vexxhost/magnum-cluster-api/commit/730743efe4ecd1233033fd7fa8119076981e4d01))
* cluster creation ([62b89f0](https://github.com/vexxhost/magnum-cluster-api/commit/62b89f0561d1ab0d14086a85181aabbed71380ac))
* Convert Openstack volume type name to valid rfc1123 string ([7d0f316](https://github.com/vexxhost/magnum-cluster-api/commit/7d0f316c85189f69ebe0787e3d24edb2b733501d))
* correct 1.25 autoscaler image ([52a756c](https://github.com/vexxhost/magnum-cluster-api/commit/52a756c0c6d73d247251de4ee8324b3eecd969b8))
* correct dependency list ([65e2ea1](https://github.com/vexxhost/magnum-cluster-api/commit/65e2ea1f5ff3e6ea8287b97f14af8111d84f5f4c))
* correct images ([df45fc4](https://github.com/vexxhost/magnum-cluster-api/commit/df45fc4d2a89afde952eac9170a2f1b7f079fd43))
* CREATE_COMPLETE state ([898c818](https://github.com/vexxhost/magnum-cluster-api/commit/898c818f354394d5ff898c2f911fa0f88b6771f1))
* **csi:** Use up-to-date provisioner name for Cinder CSI ([#295](https://github.com/vexxhost/magnum-cluster-api/issues/295)) ([79a0ce2](https://github.com/vexxhost/magnum-cluster-api/commit/79a0ce25633d8ea91a072ef1442aeb58db7e5111))
* deploy autoscaler right before the cluster creation completed ([#307](https://github.com/vexxhost/magnum-cluster-api/issues/307)) ([a48ddef](https://github.com/vexxhost/magnum-cluster-api/commit/a48ddef4bdd238c35ff967c2025898c0bec7c59f))
* disable profiling ([d18936e](https://github.com/vexxhost/magnum-cluster-api/commit/d18936e9ae76c996c6b4ff8ecbadcf666da572b0)), closes [#30](https://github.com/vexxhost/magnum-cluster-api/issues/30) [#35](https://github.com/vexxhost/magnum-cluster-api/issues/35) [#36](https://github.com/vexxhost/magnum-cluster-api/issues/36)
* Do not upgrade helmrelease in pending status ([81bb06c](https://github.com/vexxhost/magnum-cluster-api/commit/81bb06c054d4c7fa2f199171be6d58b2a5e16cf4))
* **doc:** Fix k8s version string ([b1f371c](https://github.com/vexxhost/magnum-cluster-api/commit/b1f371cd36d8de041b50674006e856e5bed36a04))
* **doc:** nit picking for README ([848e016](https://github.com/vexxhost/magnum-cluster-api/commit/848e016094aa21e767d03f08bbc8f1d05adb6a18))
* Drop MachineDeployment annotation workaround [#142](https://github.com/vexxhost/magnum-cluster-api/issues/142) ([e3981ed](https://github.com/vexxhost/magnum-cluster-api/commit/e3981ed1b7790b19343d326e20bab43e8f8b507f))
* enable ssl access ([7251c8a](https://github.com/vexxhost/magnum-cluster-api/commit/7251c8a240a90dcc1dac3abd28450aca591a3684))
* first pass at upgrades ([28ce8b0](https://github.com/vexxhost/magnum-cluster-api/commit/28ce8b0fddc2ea4447dbedc7db1df9763a823794))
* fix audit log enabled clusters ([#276](https://github.com/vexxhost/magnum-cluster-api/issues/276)) ([ef1a1ff](https://github.com/vexxhost/magnum-cluster-api/commit/ef1a1ffb71cb5584466d201c4d25d49bb0cffa1e))
* fix cluster status when update done ([#322](https://github.com/vexxhost/magnum-cluster-api/issues/322)) ([9c237d1](https://github.com/vexxhost/magnum-cluster-api/commit/9c237d1f37f94ac922efe22fe65e6aac74a1234c))
* fix jsonpatch for preKubeadmCommands ([#331](https://github.com/vexxhost/magnum-cluster-api/issues/331)) ([6fcf823](https://github.com/vexxhost/magnum-cluster-api/commit/6fcf823e8e71a807d90f91db5b59dd2a748daad0))
* Fix manila csi config ([#254](https://github.com/vexxhost/magnum-cluster-api/issues/254)) ([867efdb](https://github.com/vexxhost/magnum-cluster-api/commit/867efdb40b646d472366e21db8187ad4d7f2f216))
* Fix the certificate deletion ([17c243a](https://github.com/vexxhost/magnum-cluster-api/commit/17c243a906cdbf14e8fe74f60f3f5f8166eb3c82))
* Fix tls-insecure of ccm configuration ([5c9ad68](https://github.com/vexxhost/magnum-cluster-api/commit/5c9ad68e4aa7ec9ba087bf4330ef9f805a15250e))
* Fix typo in developer guide doc ([ff59cbb](https://github.com/vexxhost/magnum-cluster-api/commit/ff59cbb4a086a7bf63e01927915ca72438ab6351))
* **helm:** make upgrades more robust ([d42696d](https://github.com/vexxhost/magnum-cluster-api/commit/d42696d70f353a8aa5ac42506d92db03ad93cfaf))
* **helm:** skip deploying autoscaler unnecessarily ([6299ec5](https://github.com/vexxhost/magnum-cluster-api/commit/6299ec55c499ac62e0bb9e9402d471c73fc9109f))
* **helm:** upgrade path ([5b9bbca](https://github.com/vexxhost/magnum-cluster-api/commit/5b9bbcad90c9530cd76bdba850c0e455efe027bd))
* image builds ([434f57d](https://github.com/vexxhost/magnum-cluster-api/commit/434f57da1cd5f7e2a9e29c770acdde57678b0fd7))
* incorrect case ([ab16448](https://github.com/vexxhost/magnum-cluster-api/commit/ab16448e99198510b40e989ace2aaa4fc0c61a8b))
* incorrect print command ([a555440](https://github.com/vexxhost/magnum-cluster-api/commit/a5554401fbd2844b5b09cd74d3491c856a9ddd2b))
* **mhc:** increase max unhealthy to 80% ([700a19c](https://github.com/vexxhost/magnum-cluster-api/commit/700a19cc52bbf6a62983b3fbb6395eea5b2fa3b5))
* move mhc to clusterclass ([c43ae93](https://github.com/vexxhost/magnum-cluster-api/commit/c43ae930db7d7e13cedfd8dd80b1ede0fd0dc4a4))
* name replacement for new repo ([0eaeeba](https://github.com/vexxhost/magnum-cluster-api/commit/0eaeeba06bf3161260cb139a5da45a4755dcb3f0))
* only add cluster uuid to labels ([76099d4](https://github.com/vexxhost/magnum-cluster-api/commit/76099d44d7c069a07a16e696fde8bec2076cb50d))
* only set replicas if auto scaling is disabled ([a6a4bf4](https://github.com/vexxhost/magnum-cluster-api/commit/a6a4bf4b0a606a71b424cabebcbfd992d582e962))
* optimize + improve registry builds ([eeb61d2](https://github.com/vexxhost/magnum-cluster-api/commit/eeb61d2441161eb6fe1f8c5e26b1a1c6fd2d2f09))
* pre-delete lbs ([513d0ff](https://github.com/vexxhost/magnum-cluster-api/commit/513d0ff5118f33ab025e512001f71baf3e1675c9)), closes [#6](https://github.com/vexxhost/magnum-cluster-api/issues/6)
* reconcile ng status ([1221e94](https://github.com/vexxhost/magnum-cluster-api/commit/1221e94e71cc88fa70839004c705af37e80ae99f))
* refactor to using handlers with context ([9e5cb2d](https://github.com/vexxhost/magnum-cluster-api/commit/9e5cb2ded67aac22dcb3512c92b74bf07a96841a))
* relax pykube-ng requirement ([10be62a](https://github.com/vexxhost/magnum-cluster-api/commit/10be62a3786312845cd6959db4a3e00eb4073da4))
* remove completed todo ([0d4bf03](https://github.com/vexxhost/magnum-cluster-api/commit/0d4bf034195a72276a17a05853bef85b37a52a00))
* remove deleted nodegroups ([66c650f](https://github.com/vexxhost/magnum-cluster-api/commit/66c650faf481058261e2befe917bfc1d289f8a39))
* remove tracebacks for missing objects ([a148d4f](https://github.com/vexxhost/magnum-cluster-api/commit/a148d4f89744b01c6e29c4f1ecbd723230f6b21c)), closes [#68](https://github.com/vexxhost/magnum-cluster-api/issues/68)
* replace the repository name ([bda20a2](https://github.com/vexxhost/magnum-cluster-api/commit/bda20a23d1845f022091029e0ed10598e07c1a94))
* resolve resize_cluster ([7efa4f9](https://github.com/vexxhost/magnum-cluster-api/commit/7efa4f92cbe2b1b73cbe50417113b9fb0b108ae5))
* respect `availability_zone` for control plane ([#313](https://github.com/vexxhost/magnum-cluster-api/issues/313)) ([6803bd3](https://github.com/vexxhost/magnum-cluster-api/commit/6803bd3f705188b476df28f4ee2bb76bedbf3541))
* respect verify_ca and openstack_ca ([107cc2f](https://github.com/vexxhost/magnum-cluster-api/commit/107cc2f302ddf41dfa4080cd6034a93639184f59))
* return helm output ([95c32a7](https://github.com/vexxhost/magnum-cluster-api/commit/95c32a79bdb1630365b951176e1c6c9fbc50d93c))
* Set MachineDeployment replicas as min node count when autoscale enabled ([3cc9b19](https://github.com/vexxhost/magnum-cluster-api/commit/3cc9b195d3964491983063a669af60037490dd63))
* Set nodegroup labels always ([5d5afa5](https://github.com/vexxhost/magnum-cluster-api/commit/5d5afa55331df5dbdfa970d4fc142d34e1163a86))
* set nodeVolumeDetachTimeout property for machines ([c52f3e7](https://github.com/vexxhost/magnum-cluster-api/commit/c52f3e7d90d5a18852d1c189f6c3095395f4ac88))
* Set the cluster status as in_progress at the end of update_nodegroup handler ([9d3312c](https://github.com/vexxhost/magnum-cluster-api/commit/9d3312c3e542b5764b8643453cd0efa052efd082))
* Skip delete_cluster when stack_id is none ([cabd872](https://github.com/vexxhost/magnum-cluster-api/commit/cabd8729b64d8a716f8b970a1d91234c279a03b4)), closes [#126](https://github.com/vexxhost/magnum-cluster-api/issues/126)
* solve black conflict ([e17ca40](https://github.com/vexxhost/magnum-cluster-api/commit/e17ca4088f1abd4c5ee6b7ee481f2117fadf5057))
* solve cinder-csi usage ([8e9157b](https://github.com/vexxhost/magnum-cluster-api/commit/8e9157b8974a02ed92cf41cd36d4014241f7083c))
* solve cluster delete sync ([53048c8](https://github.com/vexxhost/magnum-cluster-api/commit/53048c8de81cbef0e643aea94dd62e23d222a455))
* solve proxied service cleanup ([476d1f7](https://github.com/vexxhost/magnum-cluster-api/commit/476d1f745b4588303cf52f48cddf07f2c11fdba0))
* solve proxy issue with ovn ([#302](https://github.com/vexxhost/magnum-cluster-api/issues/302)) ([5b4bad4](https://github.com/vexxhost/magnum-cluster-api/commit/5b4bad49415d6daa5df7399d77d364c8839d7a87))
* solve race condition for stack_id ([43474f1](https://github.com/vexxhost/magnum-cluster-api/commit/43474f1c81cc1268afdac4f4f21681ded28fcfa4))
* stop adding cluster name to node name ([0024683](https://github.com/vexxhost/magnum-cluster-api/commit/002468379a0ffd8cc20490477e46ac43bacb6478)), closes [#96](https://github.com/vexxhost/magnum-cluster-api/issues/96)
* stop docker from tinkering ([6fdf1d2](https://github.com/vexxhost/magnum-cluster-api/commit/6fdf1d2312d66f7e087c74ea74b9ad0be3d874cc))
* stop unexpected rollouts ([#324](https://github.com/vexxhost/magnum-cluster-api/issues/324)) ([78f8a02](https://github.com/vexxhost/magnum-cluster-api/commit/78f8a02691b5dc25dd82d0747d8050bf85b9ede4))
* support py3.6+ ([4e1e0b5](https://github.com/vexxhost/magnum-cluster-api/commit/4e1e0b58c264632a1af7ae198c1d1b768330f38f))
* test image loader ([7e7b30c](https://github.com/vexxhost/magnum-cluster-api/commit/7e7b30c57f8cd5ad16bf71d84fc6a2c99cb5e7c7))
* Update cluster-autoscaler chart version to support k8s 1.27 ([#192](https://github.com/vexxhost/magnum-cluster-api/issues/192)) ([883968a](https://github.com/vexxhost/magnum-cluster-api/commit/883968a555e31039fe014522621f7eb50c1c261e))
* update repo for initContainers ([f66bb4b](https://github.com/vexxhost/magnum-cluster-api/commit/f66bb4b450736ef38656a1091c4a794d0b7f560f))
* upgrades ([bda670d](https://github.com/vexxhost/magnum-cluster-api/commit/bda670d25ae78f1d1e3e3afafd17ccaaebc959cf))
* use 20.04 by default ([0af2de3](https://github.com/vexxhost/magnum-cluster-api/commit/0af2de3c5a4ce4600bcc28be944edef19a887dfd))
* use api from arg ([386eead](https://github.com/vexxhost/magnum-cluster-api/commit/386eeadd6614cb30d108ba42fb3456da226d5f34))
* use apply patch strategy for kube api resource update ([904abff](https://github.com/vexxhost/magnum-cluster-api/commit/904abff90ec5c0b89c25f1f8f3912abd3e7a049e))
* use azure dns + fix subnet mismatch ([16d75c6](https://github.com/vexxhost/magnum-cluster-api/commit/16d75c6be0bc7690b9cade2d1198dcf80b43d1fa))
* use capi to determine health ([#226](https://github.com/vexxhost/magnum-cluster-api/issues/226)) ([d599617](https://github.com/vexxhost/magnum-cluster-api/commit/d599617fcc9620d989446b3a8e9875a958b1c725))
* use correct sandbox_image ([80d74d2](https://github.com/vexxhost/magnum-cluster-api/commit/80d74d26d5d341c0042a794a2f5ab7151952442c))
* use dynamic `ClusterClass` version ([d7fbbf0](https://github.com/vexxhost/magnum-cluster-api/commit/d7fbbf0665178028a79d2f184adcf1f55e68dcd4)), closes [#16](https://github.com/vexxhost/magnum-cluster-api/issues/16)
* use endpoint_type for nova ([688d844](https://github.com/vexxhost/magnum-cluster-api/commit/688d84408efcebd0dfcde6648b2db8c5a7cce1c9))
* use getpass.getuser ([67e1ec5](https://github.com/vexxhost/magnum-cluster-api/commit/67e1ec5b70f5b2ebbcb5b773b6a09cb249cfd0f9))
* use locking for status update ([#318](https://github.com/vexxhost/magnum-cluster-api/issues/318)) ([dcceec4](https://github.com/vexxhost/magnum-cluster-api/commit/dcceec4ed017914c94b8bbe011cde4654c503793))
* use new registry + 1.26.2 images ([b6c814f](https://github.com/vexxhost/magnum-cluster-api/commit/b6c814f503b939ae48ed97a8b86f003f7b9346e1))
* use nova_client interface ([5dc34f3](https://github.com/vexxhost/magnum-cluster-api/commit/5dc34f3e28c7e9246c6b35eebb232cddeda64a5e))
* use operating_system ([062e7f3](https://github.com/vexxhost/magnum-cluster-api/commit/062e7f3390ccf3fecc26c045f6eaed2adb9619a4))
* Use public auth_url for CloudConfigSecret ([4f9c852](https://github.com/vexxhost/magnum-cluster-api/commit/4f9c852597b2631ec1cf6cea6e5afbe86b68fb21))
* Wait until observedGeneration of the capi cluster is increased in cluster upgrade ([58b6325](https://github.com/vexxhost/magnum-cluster-api/commit/58b632569496961ac9ffb09c00e043627791bb6e)), closes [#57](https://github.com/vexxhost/magnum-cluster-api/issues/57)


### Documentation

* add dashboard docs ([2ae4adb](https://github.com/vexxhost/magnum-cluster-api/commit/2ae4adb4f178a340b4f922f7d50cb100d6a5fcd5))
* add devstack docs ([3dc6c69](https://github.com/vexxhost/magnum-cluster-api/commit/3dc6c6997ab29147d9185fd860c4345017a51719))
* add etcd_volume_{size,type} docs ([3f1a636](https://github.com/vexxhost/magnum-cluster-api/commit/3f1a636cb70f5a6aa41178945b71cb18e2729661))
* add links to new images ([4fd698f](https://github.com/vexxhost/magnum-cluster-api/commit/4fd698f21a38df58ceb98fda12f673ea7114efbd))
* added basic troubleshooting docs ([f2f2983](https://github.com/vexxhost/magnum-cluster-api/commit/f2f2983c059334f18b94da272a99faa9efd2f46d))
* added devstack info ([e8059d9](https://github.com/vexxhost/magnum-cluster-api/commit/e8059d9d6651dbdb9dbbccfa2ac961e957212144))
* added info where to install crane ([084d191](https://github.com/vexxhost/magnum-cluster-api/commit/084d191253a6050b202f1c080fa68b06c51ff100))
* fix typos ([27b94c3](https://github.com/vexxhost/magnum-cluster-api/commit/27b94c3b80e822cb605513fb85d7d7df21f33817))
* refactor into tabs ([8c0cbbb](https://github.com/vexxhost/magnum-cluster-api/commit/8c0cbbbb310bfaff01509585c2b0036631d8a065))
* remove broken 1.26.2 images ([42f8a5f](https://github.com/vexxhost/magnum-cluster-api/commit/42f8a5f9a5221b8b7609c9524c1a079ac919d6b8))
* update adding images ([d90ba3c](https://github.com/vexxhost/magnum-cluster-api/commit/d90ba3c53571dfa382e3d044c2dd5ce2c1d759ed))


### Miscellaneous Chores

* release 0.11.1 ([36b9319](https://github.com/vexxhost/magnum-cluster-api/commit/36b931918b28ae4db526550290ae7a4201dff0d8))
* release 0.11.2 ([9d10552](https://github.com/vexxhost/magnum-cluster-api/commit/9d10552125494bcf3bffafea35429f6c6439b1f0))
* release 0.15.0 ([50121a6](https://github.com/vexxhost/magnum-cluster-api/commit/50121a607fa1ab29a269d86b105c7a1c1a6e3611))
* release 0.15.1 ([0f89859](https://github.com/vexxhost/magnum-cluster-api/commit/0f898598702f0de98d6ef47829f39205c2cea4df))
* release 0.2.0 ([9c8fe82](https://github.com/vexxhost/magnum-cluster-api/commit/9c8fe8252e61b43019a0c45d31284467ec99af15))

## [0.15.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.14.2...v0.15.0) (2024-03-19)


### Features

* RockyLinux 8/9 support ([#326](https://github.com/vexxhost/magnum-cluster-api/issues/326)) ([2a53f3e](https://github.com/vexxhost/magnum-cluster-api/commit/2a53f3e340524deee3ddbf08b41071fba070d7d3))


### Bug Fixes

* add k8s-keystone-auth to image ([0c6ca67](https://github.com/vexxhost/magnum-cluster-api/commit/0c6ca67d5a98f0d404d9dd28b3bfb9e443c937be))
* fix jsonpatch for preKubeadmCommands ([#331](https://github.com/vexxhost/magnum-cluster-api/issues/331)) ([6fcf823](https://github.com/vexxhost/magnum-cluster-api/commit/6fcf823e8e71a807d90f91db5b59dd2a748daad0))


### Documentation

* add etcd_volume_{size,type} docs ([3f1a636](https://github.com/vexxhost/magnum-cluster-api/commit/3f1a636cb70f5a6aa41178945b71cb18e2729661))

## [0.14.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.14.1...v0.14.2) (2024-03-17)


### Bug Fixes

* stop unexpected rollouts ([#324](https://github.com/vexxhost/magnum-cluster-api/issues/324)) ([78f8a02](https://github.com/vexxhost/magnum-cluster-api/commit/78f8a02691b5dc25dd82d0747d8050bf85b9ede4))

## [0.14.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.14.0...v0.14.1) (2024-03-14)


### Bug Fixes

* fix cluster status when update done ([#322](https://github.com/vexxhost/magnum-cluster-api/issues/322)) ([9c237d1](https://github.com/vexxhost/magnum-cluster-api/commit/9c237d1f37f94ac922efe22fe65e6aac74a1234c))

## [0.14.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.13.4...v0.14.0) (2024-03-08)


### Features

* support etcd volume ([#305](https://github.com/vexxhost/magnum-cluster-api/issues/305)) ([544cb77](https://github.com/vexxhost/magnum-cluster-api/commit/544cb77a4a2101dc2af6ee940ab05968f015fc1a))
* support keystone-auth ([#297](https://github.com/vexxhost/magnum-cluster-api/issues/297)) ([50a2c27](https://github.com/vexxhost/magnum-cluster-api/commit/50a2c277be084fefcc7a53c9309716771c003ea8))
* upgrade capi version ([#299](https://github.com/vexxhost/magnum-cluster-api/issues/299)) ([83535e7](https://github.com/vexxhost/magnum-cluster-api/commit/83535e7405e1a1ef1ce0251694eec78882873838))


### Bug Fixes

* deploy autoscaler right before the cluster creation completed ([#307](https://github.com/vexxhost/magnum-cluster-api/issues/307)) ([a48ddef](https://github.com/vexxhost/magnum-cluster-api/commit/a48ddef4bdd238c35ff967c2025898c0bec7c59f))
* respect `availability_zone` for control plane ([#313](https://github.com/vexxhost/magnum-cluster-api/issues/313)) ([6803bd3](https://github.com/vexxhost/magnum-cluster-api/commit/6803bd3f705188b476df28f4ee2bb76bedbf3541))
* use locking for status update ([#318](https://github.com/vexxhost/magnum-cluster-api/issues/318)) ([dcceec4](https://github.com/vexxhost/magnum-cluster-api/commit/dcceec4ed017914c94b8bbe011cde4654c503793))

## [0.13.4](https://github.com/vexxhost/magnum-cluster-api/compare/v0.13.3...v0.13.4) (2024-01-31)


### Bug Fixes

* **csi:** Use up-to-date provisioner name for Cinder CSI ([#295](https://github.com/vexxhost/magnum-cluster-api/issues/295)) ([79a0ce2](https://github.com/vexxhost/magnum-cluster-api/commit/79a0ce25633d8ea91a072ef1442aeb58db7e5111))
* solve proxy issue with ovn ([#302](https://github.com/vexxhost/magnum-cluster-api/issues/302)) ([5b4bad4](https://github.com/vexxhost/magnum-cluster-api/commit/5b4bad49415d6daa5df7399d77d364c8839d7a87))

## [0.13.3](https://github.com/vexxhost/magnum-cluster-api/compare/v0.13.2...v0.13.3) (2023-12-27)


### Bug Fixes

* incorrect case ([ab16448](https://github.com/vexxhost/magnum-cluster-api/commit/ab16448e99198510b40e989ace2aaa4fc0c61a8b))
* only set replicas if auto scaling is disabled ([a6a4bf4](https://github.com/vexxhost/magnum-cluster-api/commit/a6a4bf4b0a606a71b424cabebcbfd992d582e962))

## [0.13.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.13.1...v0.13.2) (2023-12-15)


### Bug Fixes

* fix audit log enabled clusters ([#276](https://github.com/vexxhost/magnum-cluster-api/issues/276)) ([ef1a1ff](https://github.com/vexxhost/magnum-cluster-api/commit/ef1a1ffb71cb5584466d201c4d25d49bb0cffa1e))

## [0.13.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.13.0...v0.13.1) (2023-12-07)


### Bug Fixes

* add unit tests for image loader + missing images ([#268](https://github.com/vexxhost/magnum-cluster-api/issues/268)) ([5223b93](https://github.com/vexxhost/magnum-cluster-api/commit/5223b93c19e22b4e7d01a4d44bf0e720ca966832))

## [0.13.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.12.1...v0.13.0) (2023-12-06)


### Features

* Support tls-cipher-suite configuration for kubelet ([5010c9a](https://github.com/vexxhost/magnum-cluster-api/commit/5010c9a4dd2c2656089b5807c38d95aec8c6ef0a))

## [0.12.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.12.0...v0.12.1) (2023-12-05)


### Bug Fixes

* allow configuring tls-cipher-suites ([#261](https://github.com/vexxhost/magnum-cluster-api/issues/261)) ([d1b7ab5](https://github.com/vexxhost/magnum-cluster-api/commit/d1b7ab5c2ea42eea35bfc87ede39ecd867ec94cf)), closes [#251](https://github.com/vexxhost/magnum-cluster-api/issues/251)
* Fix typo in developer guide doc ([ff59cbb](https://github.com/vexxhost/magnum-cluster-api/commit/ff59cbb4a086a7bf63e01927915ca72438ab6351))
* set nodeVolumeDetachTimeout property for machines ([c52f3e7](https://github.com/vexxhost/magnum-cluster-api/commit/c52f3e7d90d5a18852d1c189f6c3095395f4ac88))
* Update cluster-autoscaler chart version to support k8s 1.27 ([#192](https://github.com/vexxhost/magnum-cluster-api/issues/192)) ([883968a](https://github.com/vexxhost/magnum-cluster-api/commit/883968a555e31039fe014522621f7eb50c1c261e))

## [0.12.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.11.2...v0.12.0) (2023-11-16)


### Features

* Fetch node count from md object when autoscaling enabled ([d64ca86](https://github.com/vexxhost/magnum-cluster-api/commit/d64ca8637da2e181143f3156a07b0ca3abe10e97))


### Bug Fixes

* address status changes for v1alpha7 ([5da7223](https://github.com/vexxhost/magnum-cluster-api/commit/5da72233baa3af3935f4624bd67894c68f5aa338))
* Convert Openstack volume type name to valid rfc1123 string ([7d0f316](https://github.com/vexxhost/magnum-cluster-api/commit/7d0f316c85189f69ebe0787e3d24edb2b733501d))
* Fix manila csi config ([#254](https://github.com/vexxhost/magnum-cluster-api/issues/254)) ([867efdb](https://github.com/vexxhost/magnum-cluster-api/commit/867efdb40b646d472366e21db8187ad4d7f2f216))
* Set MachineDeployment replicas as min node count when autoscale enabled ([3cc9b19](https://github.com/vexxhost/magnum-cluster-api/commit/3cc9b195d3964491983063a669af60037490dd63))
* solve cluster delete sync ([53048c8](https://github.com/vexxhost/magnum-cluster-api/commit/53048c8de81cbef0e643aea94dd62e23d222a455))
* solve proxied service cleanup ([476d1f7](https://github.com/vexxhost/magnum-cluster-api/commit/476d1f745b4588303cf52f48cddf07f2c11fdba0))

## [0.11.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.11.1...v0.11.2) (2023-11-06)


### Features

* Validate fixed_network and fixed_subnet existence ([46ac9ac](https://github.com/vexxhost/magnum-cluster-api/commit/46ac9ac4ed288eac964af647d60d21d7865599c9))


### Bug Fixes

* Set nodegroup labels always ([5d5afa5](https://github.com/vexxhost/magnum-cluster-api/commit/5d5afa55331df5dbdfa970d4fc142d34e1163a86))


### Miscellaneous Chores

* release 0.11.2 ([9d10552](https://github.com/vexxhost/magnum-cluster-api/commit/9d10552125494bcf3bffafea35429f6c6439b1f0))

## [0.11.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.11.0...v0.11.1) (2023-10-13)


### Miscellaneous Chores

* release 0.11.1 ([36b9319](https://github.com/vexxhost/magnum-cluster-api/commit/36b931918b28ae4db526550290ae7a4201dff0d8))

## [0.11.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.10.0...v0.11.0) (2023-10-02)


### Features

* Support endpoint configuration for cluster-api ([#211](https://github.com/vexxhost/magnum-cluster-api/issues/211)) ([8a5ffac](https://github.com/vexxhost/magnum-cluster-api/commit/8a5ffac1e0ed3f1a7166dfd15a62b74f6a140963))
* Support Flatcar OS ([#225](https://github.com/vexxhost/magnum-cluster-api/issues/225)) ([ef4401f](https://github.com/vexxhost/magnum-cluster-api/commit/ef4401f3019d04735c0ee85e4b8057896086c70a))


### Bug Fixes

* Add cacert in cloud config ([9fbdda6](https://github.com/vexxhost/magnum-cluster-api/commit/9fbdda6f0fa95ab48a0c25baa4ef26e1c1cbea96))
* use capi to determine health ([#226](https://github.com/vexxhost/magnum-cluster-api/issues/226)) ([d599617](https://github.com/vexxhost/magnum-cluster-api/commit/d599617fcc9620d989446b3a8e9875a958b1c725))

## [0.10.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.9.1...v0.10.0) (2023-08-04)


### Features

* enable in-cluster traffic ([61bf7aa](https://github.com/vexxhost/magnum-cluster-api/commit/61bf7aa3bf1990eb0c067d4272b28305ea8eb155))


### Documentation

* refactor into tabs ([8c0cbbb](https://github.com/vexxhost/magnum-cluster-api/commit/8c0cbbbb310bfaff01509585c2b0036631d8a065))

## [0.9.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.9.0...v0.9.1) (2023-07-31)


### Documentation

* add dashboard docs ([2ae4adb](https://github.com/vexxhost/magnum-cluster-api/commit/2ae4adb4f178a340b4f922f7d50cb100d6a5fcd5))

## [0.9.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.8.1...v0.9.0) (2023-07-21)


### Features

* Add labels for nodegroup name and role name ([bfc2f52](https://github.com/vexxhost/magnum-cluster-api/commit/bfc2f5228bdc6e137918c8ee721b20a689d24f95))
* Validate flavors ([e438f4b](https://github.com/vexxhost/magnum-cluster-api/commit/e438f4b490b16b7f296e9828f1100067845cafae))


### Bug Fixes

* correct images ([df45fc4](https://github.com/vexxhost/magnum-cluster-api/commit/df45fc4d2a89afde952eac9170a2f1b7f079fd43))
* **mhc:** increase max unhealthy to 80% ([700a19c](https://github.com/vexxhost/magnum-cluster-api/commit/700a19cc52bbf6a62983b3fbb6395eea5b2fa3b5))
* refactor to using handlers with context ([9e5cb2d](https://github.com/vexxhost/magnum-cluster-api/commit/9e5cb2ded67aac22dcb3512c92b74bf07a96841a))

## [0.8.1](https://github.com/vexxhost/magnum-cluster-api/compare/v0.8.0...v0.8.1) (2023-07-07)


### Bug Fixes

* **doc:** Fix k8s version string ([b1f371c](https://github.com/vexxhost/magnum-cluster-api/commit/b1f371cd36d8de041b50674006e856e5bed36a04))
* **doc:** nit picking for README ([848e016](https://github.com/vexxhost/magnum-cluster-api/commit/848e016094aa21e767d03f08bbc8f1d05adb6a18))
* **helm:** make upgrades more robust ([d42696d](https://github.com/vexxhost/magnum-cluster-api/commit/d42696d70f353a8aa5ac42506d92db03ad93cfaf))
* **helm:** skip deploying autoscaler unnecessarily ([6299ec5](https://github.com/vexxhost/magnum-cluster-api/commit/6299ec55c499ac62e0bb9e9402d471c73fc9109f))
* optimize + improve registry builds ([eeb61d2](https://github.com/vexxhost/magnum-cluster-api/commit/eeb61d2441161eb6fe1f8c5e26b1a1c6fd2d2f09))

## [0.8.0](https://github.com/vexxhost/magnum-cluster-api/compare/v0.7.2...v0.8.0) (2023-07-04)


### Features

* add 1.27 support ([c256e74](https://github.com/vexxhost/magnum-cluster-api/commit/c256e74c4f76153b30fdaee68b92750a2e140d2f))


### Bug Fixes

* correct 1.25 autoscaler image ([52a756c](https://github.com/vexxhost/magnum-cluster-api/commit/52a756c0c6d73d247251de4ee8324b3eecd969b8))
* use azure dns + fix subnet mismatch ([16d75c6](https://github.com/vexxhost/magnum-cluster-api/commit/16d75c6be0bc7690b9cade2d1198dcf80b43d1fa))


### Documentation

* add links to new images ([4fd698f](https://github.com/vexxhost/magnum-cluster-api/commit/4fd698f21a38df58ceb98fda12f673ea7114efbd))

## [0.7.2](https://github.com/vexxhost/magnum-cluster-api/compare/v0.7.1...v0.7.2) (2023-07-02)


### Bug Fixes

* bump capi ([ba2866d](https://github.com/vexxhost/magnum-cluster-api/commit/ba2866defad25aac12f4055275251497311e4e22))
* **helm:** upgrade path ([5b9bbca](https://github.com/vexxhost/magnum-cluster-api/commit/5b9bbcad90c9530cd76bdba850c0e455efe027bd))

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
