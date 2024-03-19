def operatingSystems = ['flatcar', 'ubuntu-2204', 'rockylinux-8', 'rockylinux-9']
def kubernetesVersions = ['v1.27.8']

def buildNewImage = (env.CHANGE_ID && pullRequest.body.contains('/build-new-images'))

def integrationJobs = [:]
operatingSystems.each { operatingSystem ->
    kubernetesVersions.each { kubernetesVersion ->
        if (buildNewImage) {
            integrationJobs["${operatingSystem}-${kubernetesVersion}-build-image"] = {
                node('jammy-16c-64g') {
                    checkout scm

                    sh 'sudo apt-get install -y jq python3-pip unzip'
                    sh 'pip install -U setuptools pip'
                    sh '$HOME/.local/bin/pip3 install -e .'

                    timeout(time: 30, unit: 'MINUTES') {
                        sh "$HOME/.local/bin/magnum-cluster-api-image-builder --operating-system ${operatingSystem} --version ${kubernetesVersion}"
                    }

                    stash name: "${operatingSystem}-kube-${kubernetesVersion}.qcow2", includes: "${operatingSystem}-kube-${kubernetesVersion}.qcow2"
                }
            }
        }

        integrationJobs["${operatingSystem}-${kubernetesVersion}-run-sonobuoy"] = {
            node('jammy-16c-64g') {
                checkout scm

                sh './hack/stack.sh'

                // TODO(mnaser): Change this logic to wait for the actual job properly
                if (buildNewImage) {
                    retry(count: 30) {
                        sleep 60
                        unstash "${operatingSystem}-kube-${kubernetesVersion}.qcow2"
                    }
                }

                withEnv([
                    "KUBE_TAG=${kubernetesVersion}",
                    "OS_DISTRO=${operatingSystem}",
                    "NODE_COUNT=2",
                    "BUILD_NEW_IMAGE=${buildNewImage}"
                ]) {
                    sh './hack/run-functional-tests.sh'
                }

                archiveArtifacts artifacts: 'sonobuoy-results.tar.gz'
                archiveArtifacts artifacts: "${operatingSystem}-kube-${kubernetesVersion}.qcow2"
            }
        }
    }
}

parallel integrationJobs