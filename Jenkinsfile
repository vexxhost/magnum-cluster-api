def operatingSystems = ['flatcar', 'ubuntu-2204', 'rockylinux-8', 'rockylinux-9']
def kubernetesVersions = ['v1.27.8']

def buildNewImage = (env.CHANGE_ID && pullRequest.body.contains('/build-new-images'))

def jobs = [:]

jobs['unit'] = {
    node('jammy-2c-8g') {
        checkout scm

        sh "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"

        sh 'sudo apt-get install -y python3-pip'
        sh 'sudo pip install hatch'
        
        try {
            sh 'hatch run test:unit --junit-xml=junit.xml'
        } finally {
            step([$class: 'JUnitResultArchiver', testResults: 'junit.xml'])
        }
    }
}

jobs['functional'] = {
    node('jammy-2c-8g') {
        checkout scm

        sh "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"

        sh 'sudo apt-get install -y python3-pip'
        sh 'sudo pip install hatch'

        sh './hack/setup-kubectl.sh'
        sh './hack/setup-helm.sh'
        sh './hack/setup-docker.sh'
        sh './hack/setup-kind.sh'
        sh './hack/setup-capo.sh'

        try {
            sh 'hatch run test:functional --junit-xml=junit.xml'
        } finally {
            step([$class: 'JUnitResultArchiver', testResults: 'junit.xml'])
        }
    }
}

operatingSystems.each { operatingSystem ->
    kubernetesVersions.each { kubernetesVersion ->
        if (buildNewImage) {
            jobs["${operatingSystem}-${kubernetesVersion}-build-image"] = {
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

        jobs["${operatingSystem}-${kubernetesVersion}-run-sonobuoy"] = {
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
                    sh './hack/run-integration-tests.sh'
                }

                archiveArtifacts artifacts: 'sonobuoy-results.tar.gz'
            }
        }
    }
}

properties([
    disableConcurrentBuilds(abortPrevious: true)
])

parallel jobs
