# Testing & Development

In order to be able to test and develop the `magnum-cluster-api` project, you
will need to have an existing Magnum deployment.  You can use the following
steps to be able to test and develop the project.

1. Start up a DevStack environment with all Cluster API dependencies

   ```bash
   ./hack/stack.sh
   ```

1. Upload an image to use with Magnum and create cluster templates

   ```bash
   pushd /tmp
   source /opt/stack/openrc
   export OS_DISTRO=ubuntu # you can change this to "flatcar" if you want to use Flatcar
   for version in v1.24.16 v1.25.12 v1.26.7 v1.27.4; do \
      [[ "${OS_DISTRO}" == "ubuntu" ]] && IMAGE_NAME="ubuntu-2204-kube-${version}" || IMAGE_NAME="flatcar-kube-${version}"; \
      curl -LO https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/${IMAGE_NAME}.qcow2; \
      openstack image create ${IMAGE_NAME} --disk-format=qcow2 --container-format=bare --property os_distro=${OS_DISTRO} --file=${IMAGE_NAME}.qcow2; \
      openstack coe cluster template create \
        --image $(openstack image show ${IMAGE_NAME} -c id -f value) \
        --external-network public \
        --dns-nameserver 8.8.8.8 \
        --master-lb-enabled \
        --master-flavor m1.medium \
        --flavor m1.medium \
        --network-driver calico \
        --docker-storage-driver overlay2 \
        --coe kubernetes \
        --label kube_tag=${version} \
        k8s-${version};
   done;
   popd
   ```

1. Spin up a new cluster using the Cluster API driver

   ```bash
   openstack coe cluster create \
     --cluster-template k8s-v1.25.12 \
     --master-count 3 \
     --node-count 2 \
     k8s-v1.25.12
   ```

1. Once the cluster reaches `CREATE_COMPLETE` state, you can interact with it:

   ```bash
   eval $(openstack coe cluster config k8s-v1.25.12)
   ```

## Conformance Testing

The project supports running Kubernetes conformance tests using [Hydrophone](https://github.com/kubernetes-sigs/hydrophone),
which generates artifacts that can be submitted to the CNCF for Kubernetes conformance certification.

Hydrophone has been validated to generate the required output files:
- `e2e.log` - Full test execution logs
- `junit_01.xml` - JUnit test results in XML format

### Running Conformance Tests

Conformance tests can be run in two ways:

#### 1. Manual Workflow Dispatch

You can manually trigger conformance tests through the GitHub Actions workflow:

1. Go to the Actions tab in the GitHub repository
2. Select the "conformance" workflow
3. Click "Run workflow"
4. Tests will run for all maintained Kubernetes versions and both network drivers (calico and cilium)

#### 2. Scheduled Runs

Conformance tests run automatically on a weekly schedule (Mondays at 2 AM UTC) to ensure
continuous compliance with Kubernetes conformance requirements.

### Running Conformance Tests Locally

To run conformance tests against an OpenStack-deployed cluster:

```bash
export OS_CLOUD=devstack
export IMAGE_NAME=ubuntu-22.04-v1.32.10
export KUBE_TAG=v1.32.10
export NETWORK_DRIVER=calico
./hack/run-conformance-tests.sh
```

This will:
- Create a Kubernetes cluster using Magnum
- Run the full Kubernetes conformance test suite
- Generate CNCF-compliant artifacts (e2e.log, junit_01.xml)
- Package the results into `conformance-results.tar.gz`

**Note**: For CNCF submission, you'll also need to create a `PRODUCT.yaml` file and `README.md`
following the [CNCF instructions](https://github.com/cncf/k8s-conformance/blob/master/instructions.md).

### Conformance Artifacts

The conformance workflow uploads the following artifacts to GitHub:

- **conformance-results-k8s-vX.Y.Z-driver**: Complete conformance test results tarball
- **cncf-submission-k8s-vX.Y.Z-driver**: Individual files for CNCF submission
  - `e2e.log`: Full test execution logs
  - `junit_01.xml`: JUnit test results

These artifacts can be downloaded and submitted to the
[CNCF k8s-conformance repository](https://github.com/cncf/k8s-conformance)
following the [instructions](https://github.com/cncf/k8s-conformance/blob/master/instructions.md).
You will need to add a `PRODUCT.yaml` file and `README.md` as described in the CNCF instructions.
