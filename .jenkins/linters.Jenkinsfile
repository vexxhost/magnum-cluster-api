pipeline {
  agent 'jammy-2c-8g'

  options {
    ansiColor('xterm')
  }

  stages {
    stage('black') {
      steps {
        sh 'sudo apt-get update'
        sh 'sudo apt-get install -y python3-pip'
        sh 'pip install black'

        withEnv(['PATH+LOCAL_BIN=$HOME/.local/bin']) {
          sh 'black --check --diff --color .'
        }
      }
    }
  }
}
