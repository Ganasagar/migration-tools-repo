#!/usr/bin/env groovy

@Library("sec_ci_libs@v2-latest") _

def aws_id = string(credentialsId: "1ddc25d8-0873-4b6f-949a-ae803b074e7a", variable: "AWS_ACCESS_KEY_ID")
def aws_key = string(credentialsId: "875cfce9-90ca-4174-8720-816b4cb7f10f", variable: "AWS_SECRET_ACCESS_KEY")

pipeline {
  agent {
    dockerfile true
  }
  stages {
    stage("Unit Test") {
      parallel {
        stage("Marathon") {
          steps {
            // don't know why yet, but the runtime on CI does some magic with virtualenvs and as a quickfix we put a seemingly redundant `pipenv install` here.
            sh 'pipenv install && cd marathon && pipenv run pytest'
          }
        }
        stage("Metronome") {
          steps {
            // don't know why yet, but the runtime on CI does some magic with virtualenvs and as a quickfix we put a seemingly redundant `pipenv install` here.
            sh 'pipenv install && pipenv run pytest --doctest-modules metronome'
          }
        }
      }
    }

    // stage("Integration Test") {
    //   TODO: cluster-setup
    //   sh 'cd tests && ./run-tests.sh'
    // }
  }
}
