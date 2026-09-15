pipeline {
  agent { label 'docker2' }

  environment {
    IMAGE_NAME = 'ghcr.io/edumfa/edumfa-radius'
    REGISTRY_URL = 'https://ghcr.io'
    REGISTRY_CRED_ID = 'd7eec284-f97b-45a6-b269-a67f5f88e3db'
  }

  options {
    disableConcurrentBuilds()
    gitLabConnection('gitlab-daasi-ext')
    gitlabBuilds(builds: [ 'check', 'determine version', 'docker build', 'tests', 'docker push' ])
  }

  triggers {
    cron('0 2 * * 1-5')

    gitlab(
      triggerOnPush: false,
      triggerOnMergeRequest: true,
      triggerOnNoteRequest: true,
      noteRegex: "Jenkins please retry a build",
      ciSkip: false,
      setBuildDescription: true,
      addNoteOnMergeRequest: true,
      addCiMessage: true,
      addVoteOnMergeRequest: true,
      acceptMergeRequestOnSuccess: false,
      cancelPendingBuildsOnUpdate: true,
      branchFilterType: 'All'
    )
  }

  stages {
    stage('check') {
      steps {
        gitlabCommitStatus(name: 'check') {
          script {
            if (env.gitlabSourceBranch) {
              env.BRANCH = env.gitlabSourceBranch
              sh "git checkout ${env.BRANCH}"
            } else if (currentBuild.getBuildCauses('hudson.triggers.TimerTrigger$TimerTriggerCause')) {
              sh 'git fetch --tags --force'

              env.BRANCH = sh(
                script: 'git tag | sort -V | tail -1',
                returnStdout: true
              ).trim()

              if (!env.BRANCH) {
                error('No tag found')
              }

              sh "git checkout ${env.BRANCH}"
            }
          }
        }
      }
    }

    stage('determine version') {
      steps {
        gitlabCommitStatus(name: 'determine version') {
          script {
            def isTag = sh(
              script: "git show-ref --verify --quiet 'refs/tags/${env.BRANCH}'",
              returnStatus: true
            ) == 0

            if (isTag) {
              env.VERSION = env.BRANCH
              env.PUSH_IMAGE = 'true'
            } else {
              env.VERSION = env.BRANCH.replace('/', '-')
              env.PUSH_IMAGE = 'false'
            }

            env.FULL_IMAGE_NAME = "${env.IMAGE_NAME}:${env.VERSION}"
            echo "Version to build: ${env.VERSION}"
            echo "Push image: ${env.PUSH_IMAGE}"
          }
        }
      }
    }

    stage('docker build') {
      steps {
        gitlabCommitStatus(name: 'docker build') {
          script {
            if (env.PUSH_IMAGE == 'true') {
              sh 'docker build --pull --no-cache --label "org.opencontainers.image.version=${VERSION}" -t "${FULL_IMAGE_NAME}" .'
            } else {
              sh 'docker build --pull --no-cache -t "${FULL_IMAGE_NAME}" .'
            }
          }
        }
      }
    }

    stage('tests') {
      steps {
        gitlabCommitStatus(name: 'tests') {
          sh 'EDUMFA_RADIUS_TEST_IMAGE="${FULL_IMAGE_NAME}" uv run --python 3.11 --with-requirements tests/requirements.txt pytest'
        }
      }
    }

    stage('docker push') {
      when {
        expression {
          env.PUSH_IMAGE == 'true'
        }
      }

      steps {
        gitlabCommitStatus(name: 'docker push') {
          script {
            docker.withRegistry(env.REGISTRY_URL, env.REGISTRY_CRED_ID) {
              sh 'docker push "${FULL_IMAGE_NAME}"'
            }
          }
        }
      }
    }
  }

  post {
    always {
      sh '''
        EDUMFA_TAG=$(grep '^EDUMFA_TAG = ' tests/test_image.py | cut -d'"' -f2)
        POSTGRES_TAG=$(grep '^POSTGRES_TAG = ' tests/test_image.py | cut -d'"' -f2)

        docker image rm -f "${FULL_IMAGE_NAME}" || true
        docker image rm -f "ghcr.io/edumfa/edumfa:${EDUMFA_TAG}" || true
        docker image rm -f "postgres:${POSTGRES_TAG}" || true
      '''

      script {
        if (env.PUSH_IMAGE != 'true') {
          try {
            updateGitlabCommitStatus name: 'docker push', state: 'success'
          } catch (err) {
            echo "WARINING: Error in post stage:"
            echo err.getMessage()
          }
        }
      }
    }
  }
}