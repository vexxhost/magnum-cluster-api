pipeline {
    agent none

    options {
        disableConcurrentBuilds(abortPrevious: true);
    }

    stages {
        stage('functional') {
            matrix {
                axes {
                    axis {
                        name 'OS_DISTRO'
                        values 'flatcar', 'ubuntu-2204'
                    }

                    axis {
                        name 'KUBE_TAG'
                        values 'v1.26.11', 'v1.27.8'
                    }
                }

                agent {
                    label 'jammy-16c-64g'
                }

                stages {
                    stage('sonobuoy') {
                        steps {
                            sh './hack/stack.sh'

                            // TODO: Wait for built artifacts
                            // TODO: Download built image

                            script {
                                env.KUBE_TAG = "${KUBE_TAG}"
                                env.NODE_COUNT = 2
                                env.OS_DISTRO = "${OS_DISTRO}"

                                // if (pullRequest.body.contains('/build-new-image')) {
                                //     env.BUILD_NEW_IMAGE = 'true'
                                // }

                                sh './hack/run-functional-tests.sh'
                            }
                        }
                    }
                }

                post {
                    always {
                        archiveArtifacts artifacts: 'sonobuoy-results.tar.gz', allowEmptyArchive: true
                    }
                }
            }
        }
    }
}