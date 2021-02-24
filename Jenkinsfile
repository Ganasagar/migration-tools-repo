#!/usr/bin/env groovy

@Library("sec_ci_libs@v2-latest") _

def aws_id = string(credentialsId: "1ddc25d8-0873-4b6f-949a-ae803b074e7a", variable: "AWS_ACCESS_KEY_ID")
def aws_key = string(credentialsId: "875cfce9-90ca-4174-8720-816b4cb7f10f", variable: "AWS_SECRET_ACCESS_KEY")

pipeline {
  agent none
  environment {
    DCOS_LICENSE = credentials('8667643a-6ad9-426e-b761-27b4226983ea')
    DCOS_EE_URL = credentials('0b513aad-e0e0-4a82-95f4-309a80a02ff9')
  }
  stages {
    stage("ci") {
      agent {
        label "mesos"
      }
      steps {
        sh 'bin/ci'
      }
    }
  }
}
