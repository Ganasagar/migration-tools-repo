# Jenkins migration tool

This guide walks through the various files and their role in performing a successful migration of Jenkins on DC/OS to Jenkins on Konvoy.

## Prerequisites

- `python3` installed in the environment
- DC/OS CLI `dcos` setup to talk to a DC/OS Cluster
- Kubernetes CLI `kubectl` setup to talk to a konvoy cluster
- Basic knowledge of kubernetes, charts and Jenkins.
- Script is tested to work in Linux based environments.

## Commands

Python file located at `scripts/main.py` is the main entrypoint for the tooling used to migrate jenkins. The help menu describes the steps involved in migration:

```
➜ python3 ./jenkins/scripts/main.py --help
usage: main.py [-h] [--version] {backup,install,migrate} ...

positional arguments:
  {backup,install,migrate}
                        sub-commands available
    backup              Backup the DC/OS package data
    install             Translate the MesosCloud based config.xml to
                        KubernetesCloud based config.xml and print install
                        instructions
    migrate             Perform various operations on jobs

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
``` 

### Overview 
At a higher level, migration can be seen as three steps:

1. Backup the DC/OS Jenkins configuration, app definition, jobs locally.
2. Install Jenkins on Konvoy by translating the above downloaded configuration and adding other customization
3. Update the Jobs downloaded from Jenkins on DC/OS and copy over to Jenkins on Konvoy.

These steps are explained in following steps:

### `1.backup`

By providing a marathon app-id (defaults to `/jenkins`), all the configuration and jobs related data can be downloaded to local file system.

```
➜ python3 ./jenkins/scripts/main.py backup --help
usage: main.py backup [-h] [-t TARGET_DIR] [--app-id APP_ID] [--retain-builds]
                      [--retain-next-build-number]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        points to jenkins_home folder with a valid "jobs"
                        folder
  --app-id APP_ID       Marathon application ID
  --retain-builds       Set to retain previous builds data
  --retain-next-build-number
                        Set to retain nextBuildNumber counter
```

`TARGET_DIR` defaults to `$(pwd)/jenkins_home` and the tooling removes the builds directory by default.

### `2.install`
The `install` command generates a `TARGET_FILE` (that defaults to `$(pwd)/k8s.config.xml` ) and prints instructions on how to use it to install in Jenkins on Konvoy. Other parameters such as `namespace` and `fullname` have sensible defaults in accordance with the upstream helm chart but can be customized.

```
➜ python3 ./jenkins/scripts/main.py install --help
usage: main.py install [-h] [-c CONFIG_FILE] [-t TARGET_FILE] [-p]
                       [--namespace NAMESPACE] [--fullname FULLNAME]
                       [--uri-prefix URI_PREFIX]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG_FILE, --config-file CONFIG_FILE
                        path of the config.xml file
  -t TARGET_FILE, --target-file TARGET_FILE
                        path of the target config.xml file
  -p, --print           Print the transformed cloud config element from
                        config.xml
  --namespace NAMESPACE
                        Namespace of the jenkins pod (defaults to jenkins)
  --fullname FULLNAME   Name of the jenkins helm installation (defaults to
                        jenkins)
  --uri-prefix URI_PREFIX
                        Uri prefix for jenkins chart (defaults to /jenkins)
```                        



### `3.migrate`

The `migrate` command has two subcommands `update` and `copy` which update the jobs and then copies them to Jenkins on Kubernetes.

```
➜ python3 ./jenkins/scripts/main.py migrate --help
usage: main.py migrate [-h] {update,copy} ...

positional arguments:
  {update,copy}  Perform various operations on jobs
    update       Update the jobs by removing the mesos related build wrappers
                 and optionally disable the jobs
    copy         Copy the jobs from local file system to Jenkins master node

optional arguments:
  -h, --help     show this help message and exit
```


#### `3a.update`


This command updates the jobs by optionally disabling the jobs. This is useful during migration of multiple jobs and the user wants to enable them manually one by one. This command also performs some other cleanup on the job definitions (such as cleaning up MesosSingleUseSlave flag which does not make any sense in the Jenkins on Konvoy)

```
➜ python3 ./jenkins/scripts/main.py migrate update --help
usage: main.py migrate update [-h] [-t TARGET_DIR] [--path PATH]
                              [--disable-jobs]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        points to jenkins_home folder with a valid "jobs"
                        folder
  --path PATH           URL of the job or folder. This is the part after
                        http://<cluster-url>/service/<service-name>/<job-path-
                        here>
  --disable-jobs        If set, the job config.xml is updated to disable the
                        job by setting "<disabled>true</disabled>"
```


#### `3b.copy`

This command copies the job from user file system to the Jenkins master node filesystem.

```
➜ python3 ./jenkins/scripts/main.py migrate copy --help
usage: main.py migrate copy [-h] [-t TARGET_DIR] [--path PATH]
                            [--namespace NAMESPACE]
                            [--release-name RELEASE_NAME] [--dry-run]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        points to jenkins_home folder with a valid "jobs"
                        folder
  --path PATH           URL of the job or folder. This is the part after
                        http://<cluster-url>/service/<service-name>/<job-path-
                        here>
  --namespace NAMESPACE
                        Namespace of the jenkins installation (defaults to
                        jenkins)
  --release-name RELEASE_NAME
                        Helm release name (defaults to jenkins)
  --dry-run             Setting this flag would just print the commands
                        without executing them
```



### Sample Output

Following is a sample output of running through all the commands. Note that all the flags provided are using their default values.

`backup` the Jenkins running on DC/OS with instance id `/jenkins` to a folder named `jenkins_home`

```
➜ python3 ./jenkins/scripts/main.py backup --app-id=jenkins --target-dir=$(pwd)/jenkins_home
[2020-11-08 11:45:10,502]  INFO {main.py:25} - Downloading DC/OS package with marathon app id jenkins into target directory <user_path>/mesosphere/dcos-migration/jenkins_home
[2020-11-08 11:45:10,502]  INFO {backup.py:60} - Validating DC/OS CLI is setup correctly
[2020-11-08 11:45:13,162]  INFO {backup.py:93} - Downloading config.xml
[2020-11-08 11:45:14,301]  INFO {backup.py:95} - Downloading jobs folder
```

`translate`

```
python3 ./jenkins/scripts/main.py install -c $(pwd)/jenkins_home/config.xml -t $(pwd)/k8s.config.xml --namespace jenkins --fullname jenkins --uri-prefix=/jenkins
--------------------------------------------------
Create the following serviceaccount, roles, and rolebindings prior to running helm install:
kubectl apply -f ./jenkins/resources/serviceaccount.yaml --namespace jenkins
--------------------------------------------------
For migrating the plugins, go to "<jenkins-url>/script" and run the following script:

def skipPlugins = ["mesos", "metrics-graphite"]
Jenkins.instance.pluginManager.plugins.each{
  plugin ->
    name = plugin.getShortName()
    if (!skipPlugins.contains(name)) {
        println ("- ${name}:${plugin.getVersion()}")
    }
}

to get a list of plugins and paste the output here (type q or quit to skip this step):
- ace-editor:1.1
- ansicolor:0.7.0
- ant:1.11
- antisamy-markup-formatter:2.0
- apache-httpcomponents-client-4-api:4.5.10-2.0
- artifactory:3.6.2
- authentication-tokens:1.3
- aws-credentials:1.28
- aws-java-sdk:1.11.723
- azure-commons:1.0.4
- azure-credentials:4.0.2
- azure-vm-agents:1.5.0
- blueocean-autofavorite:1.2.4
- blueocean-bitbucket-pipeline:1.23.2
- blueocean-commons:1.23.2
- blueocean-config:1.23.2
- blueocean-core-js:1.23.2
- blueocean-dashboard:1.23.2
- blueocean-display-url:2.3.1
- blueocean-events:1.23.2
- blueocean-git-pipeline:1.23.2
- blueocean-github-pipeline:1.23.2
- blueocean-i18n:1.23.2
- blueocean-jira:1.23.2
- blueocean-jwt:1.23.2
- blueocean-personalization:1.23.2
- blueocean-pipeline-api-impl:1.23.2
- blueocean-pipeline-editor:1.23.2
- blueocean-pipeline-scm-api:1.23.2
- blueocean-rest-impl:1.23.2
- blueocean-rest:1.23.2
- blueocean-web:1.23.2
- blueocean:1.23.2
- bouncycastle-api:2.18
- branch-api:2.5.6
- build-name-setter:2.1.0
- build-timeout:1.19.1
- cloud-stats:0.25
- cloudbees-bitbucket-branch-source:2.8.0
- cloudbees-folder:6.13
- command-launcher:1.4
- conditional-buildstep:1.3.6
- config-file-provider:3.6.3
- configuration-as-code:1.36
- copyartifact:1.44
- credentials-binding:1.23
- credentials:2.3.8
- cvs:2.16
- display-url-api:2.3.2
- docker-build-publish:1.3.2
- docker-commons:1.16
- docker-workflow:1.23
- durable-task:1.34
- ec2:1.50.3
- embeddable-build-status:2.0.3
- external-monitor-job:1.7
- favorite:2.3.2
- git-client:3.2.1
- git-server:1.9
- git:4.2.2
- github-api:1.112.0
- github-branch-source:2.8.0
- github-organization-folder:1.6
- github:1.30.0
- gitlab-plugin:1.5.13
- gradle:1.36
- greenballs:1.15
- handlebars:1.1.1
- handy-uri-templates-2-api:2.1.8-1.0
- htmlpublisher:1.23
- ivy:2.1
- jackson2-api:2.11.0
- javadoc:1.5
- jdk-tool:1.4
- jenkins-design-language:1.23.2
- jira:3.0.18
- job-dsl:1.77
- jobConfigHistory:2.26
- jquery-detached:1.2.1
- jquery-ui:1.0.2
- jquery:1.12.4-1
- jsch:0.1.55.2
- junit:1.29
- ldap:1.24
- lockable-resources:2.8
- mailer:1.32
- mapdb-api:1.0.9.0
- marathon:1.6.0
- matrix-auth:2.5
- matrix-project:1.14
- maven-plugin:3.6
- mercurial:2.10
- metrics:4.0.2.6
- momentjs:1.1.1
- monitoring:1.83.0
- nant:1.4.3
- node-iterator-api:1.5.0
- pam-auth:1.6
- parameterized-trigger:2.36
- pipeline-build-step:2.12
- pipeline-github-lib:1.0
- pipeline-graph-analysis:1.10
- pipeline-input-step:2.11
- pipeline-milestone-step:1.3.1
- pipeline-model-api:1.7.0
- pipeline-model-declarative-agent:1.1.1
- pipeline-model-definition:1.7.0
- pipeline-model-extensions:1.7.0
- pipeline-rest-api:2.13
- pipeline-stage-step:2.3
- pipeline-stage-tags-metadata:1.7.0
- pipeline-stage-view:2.13
- plain-credentials:1.7
- rebuild:1.31
- prometheus:2.0.6
- pubsub-light:1.13
- role-strategy:2.16
- run-condition:1.3
- s3:0.11.5
- saferestart:0.3
- saml:1.1.6
- scm-api:2.6.3
- script-security:1.73
- sse-gateway:1.23
- ssh-agent:1.19
- ssh-credentials:1.18.1
- ssh-slaves:1.31.2
- structs:1.20
- subversion:2.13.1
- timestamper:1.11.3
- token-macro:2.12
- translation:1.16
- trilead-api:1.0.8
- variant:1.3
- windows-slaves:1.6
- workflow-aggregator:2.6
- workflow-api:2.40
- workflow-basic-steps:2.20
- workflow-cps-global-lib:2.16
- workflow-cps:2.80
- workflow-durable-task-step:2.35
- workflow-job:2.39
- workflow-multibranch:2.21
- workflow-scm-step:2.11
- workflow-step-api:2.22
- workflow-support:3.4

--------------------------------------------------
Use following values.yaml to install helm chart
cat <<EOF >> values.yaml
master:
  tag: 2.190.1
  installPlugins:
  - kubernetes:1.24.1
  csrf:
    defaultCrumbIssuer:
      enabled: false
      proxyCompatability: false
  prometheus:
    enabled: true
    serviceMonitorNamespace: "kubeaddons"
    serviceMonitorAdditionalLabels:
      app: jenkins
      release: prometheus-kubeaddons
  serviceType: "LoadBalancer"
  jenkinsUriPrefix: "/jenkins"
  ingress:
    enabled: true
    path: /jenkins
    annotations:
      kubernetes.io/ingress.class: traefik
  sidecars:
    configAutoReload:
      enabled: false
  additionalPlugins:
  - ace-editor:1.1
  - ansicolor:0.7.0
  - ant:1.11
  - antisamy-markup-formatter:2.0
  - apache-httpcomponents-client-4-api:4.5.10-2.0
  - artifactory:3.6.2
  - authentication-tokens:1.3
  - aws-credentials:1.28
  - aws-java-sdk:1.11.723
  - azure-commons:1.0.4
  - azure-credentials:4.0.2
  - azure-vm-agents:1.5.0
  - blueocean-autofavorite:1.2.4
  - blueocean-bitbucket-pipeline:1.23.2
  - blueocean-commons:1.23.2
  - blueocean-config:1.23.2
  - blueocean-core-js:1.23.2
  - blueocean-dashboard:1.23.2
  - blueocean-display-url:2.3.1
  - blueocean-events:1.23.2
  - blueocean-git-pipeline:1.23.2
  - blueocean-github-pipeline:1.23.2
  - blueocean-i18n:1.23.2
  - blueocean-jira:1.23.2
  - blueocean-jwt:1.23.2
  - blueocean-personalization:1.23.2
  - blueocean-pipeline-api-impl:1.23.2
  - blueocean-pipeline-editor:1.23.2
  - blueocean-pipeline-scm-api:1.23.2
  - blueocean-rest-impl:1.23.2
  - blueocean-rest:1.23.2
  - blueocean-web:1.23.2
  - blueocean:1.23.2
  - bouncycastle-api:2.18
  - branch-api:2.5.6
  - build-name-setter:2.1.0
  - build-timeout:1.19.1
  - cloud-stats:0.25
  - cloudbees-bitbucket-branch-source:2.8.0
  - cloudbees-folder:6.13
  - command-launcher:1.4
  - conditional-buildstep:1.3.6
  - config-file-provider:3.6.3
  - configuration-as-code:1.36
  - copyartifact:1.44
  - credentials-binding:1.23
  - credentials:2.3.8
  - cvs:2.16
  - display-url-api:2.3.2
  - docker-build-publish:1.3.2
  - docker-commons:1.16
  - docker-workflow:1.23
  - durable-task:1.34
  - ec2:1.50.3
  - embeddable-build-status:2.0.3
  - external-monitor-job:1.7
  - favorite:2.3.2
  - git-client:3.2.1
  - git-server:1.9
  - git:4.2.2
  - github-api:1.112.0
  - github-branch-source:2.8.0
  - github-organization-folder:1.6
  - github:1.30.0
  - gitlab-plugin:1.5.13
  - gradle:1.36
  - greenballs:1.15
  - handlebars:1.1.1
  - handy-uri-templates-2-api:2.1.8-1.0
  - htmlpublisher:1.23
  - ivy:2.1
  - jackson2-api:2.11.0
  - javadoc:1.5
  - jdk-tool:1.4
  - jenkins-design-language:1.23.2
  - jira:3.0.18
  - job-dsl:1.77
  - jobConfigHistory:2.26
  - jquery-detached:1.2.1
  - jquery-ui:1.0.2
  - jquery:1.12.4-1
  - jsch:0.1.55.2
  - junit:1.29
  - ldap:1.24
  - lockable-resources:2.8
  - mailer:1.32
  - mapdb-api:1.0.9.0
  - marathon:1.6.0
  - matrix-auth:2.5
  - matrix-project:1.14
  - maven-plugin:3.6
  - mercurial:2.10
  - metrics:4.0.2.6
  - momentjs:1.1.1
  - monitoring:1.83.0
  - nant:1.4.3
  - node-iterator-api:1.5.0
  - pam-auth:1.6
  - parameterized-trigger:2.36
  - pipeline-build-step:2.12
  - pipeline-github-lib:1.0
  - pipeline-graph-analysis:1.10
  - pipeline-input-step:2.11
  - pipeline-milestone-step:1.3.1
  - pipeline-model-api:1.7.0
  - pipeline-model-declarative-agent:1.1.1
  - pipeline-model-definition:1.7.0
  - pipeline-model-extensions:1.7.0
  - pipeline-rest-api:2.13
  - pipeline-stage-step:2.3
  - pipeline-stage-tags-metadata:1.7.0
  - pipeline-stage-view:2.13
  - plain-credentials:1.7
  - rebuild:1.31
  - prometheus:2.0.6
  - pubsub-light:1.13
  - role-strategy:2.16
  - run-condition:1.3
  - s3:0.11.5
  - saferestart:0.3
  - saml:1.1.6
  - scm-api:2.6.3
  - script-security:1.73
  - sse-gateway:1.23
  - ssh-agent:1.19
  - ssh-credentials:1.18.1
  - ssh-slaves:1.31.2
  - structs:1.20
  - subversion:2.13.1
  - timestamper:1.11.3
  - token-macro:2.12
  - translation:1.16
  - trilead-api:1.0.8
  - variant:1.3
  - windows-slaves:1.6
  - workflow-aggregator:2.6
  - workflow-api:2.40
  - workflow-basic-steps:2.20
  - workflow-cps-global-lib:2.16
  - workflow-cps:2.80
  - workflow-durable-task-step:2.35
  - workflow-job:2.39
  - workflow-multibranch:2.21
  - workflow-scm-step:2.11
  - workflow-step-api:2.22
  - workflow-support:3.4
EOF
--------------------------------------------------
Run the following command to install the chart:
Using helm v2:

helm install \
    --namespace jenkins \
    --name jenkins \
    -f values.yaml \
    --set serviceAccount.create=false \
    --set serviceAccount.name=jenkins \
    --set serviceAccountAgent.name=jenkins \
    --repo https://charts.jenkins.io \
    --version 2.6.4 \
    jenkins

Using helm v3:

helm install jenkins \
    --namespace jenkins \
    -f values.yaml \
    --set serviceAccount.create=false \
    --set serviceAccount.name=jenkins \
    --set serviceAccountAgent.name=jenkins \
    --repo https://charts.jenkins.io \
    --version 2.6.4 \
    jenkins

--------------------------------------------------
[2020-11-08 11:55:20,654]  INFO {main.py:143} - Translating mesos config.xml to k8s config.xml from <user_path>/mesosphere/dcos-migration/jenkins_home/config.xml to <user_path>/mesosphere/dcos-migration/k8s.config.xml
[2020-11-08 11:55:20,654]  INFO {translate.py:299} - using "<user_path>/mesosphere/dcos-migration/jenkins_home/config.xml" file to migrate to kubernetes configuration at "<user_path>/mesosphere/dcos-migration/k8s.config.xml"
[2020-11-08 11:55:20,656]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "0" with empty label
[2020-11-08 11:55:20,656] WARNING {translate.py:184} - Key "labelString" not found in "MesosCloud" cloud at slaveInfo index "0" with empty label. Defaulting to empty string.
[2020-11-08 11:55:20,656]  INFO {translate.py:239} - No portMappings found in BRIDGE mode
[2020-11-08 11:55:20,656]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "1" with label "base-dind-logan"
[2020-11-08 11:55:20,656] WARNING {translate.py:253} - Element "networking" of type "USER" not supported in k8s
[2020-11-08 11:55:20,657]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "2" with label "linux"
[2020-11-08 11:55:20,657]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "3" with label "mvn-agent"
[2020-11-08 11:55:20,657]  INFO {translate.py:239} - No portMappings found in BRIDGE mode
[2020-11-08 11:55:20,657]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "4" with label "npm-agent-logan"
[2020-11-08 11:55:20,657]  INFO {translate.py:239} - No portMappings found in BRIDGE mode
[2020-11-08 11:55:20,657]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "5" with label "tstyle-agent"
[2020-11-08 11:55:20,657]  INFO {translate.py:239} - No portMappings found in BRIDGE mode
[2020-11-08 11:55:20,658]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "6" with label "php-agent"
[2020-11-08 11:55:20,658]  INFO {translate.py:239} - No portMappings found in BRIDGE mode
[2020-11-08 11:55:20,658]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "7" with label "rust-1.47.0-logan"
[2020-11-08 11:55:20,658]  INFO {translate.py:239} - No portMappings found in BRIDGE mode
[2020-11-08 11:55:20,658]  INFO {translate.py:168} - Processing "MesosCloud" cloud at slaveInfo index "8" with label "mesos"
[2020-11-08 11:55:20,658]  INFO {translate.py:174} - No "containerInfo" found in "MesosCloud" cloud at slaveInfo index "8" with label "mesos". (probably the default node?). skipping..
[2020-11-08 11:55:20,659]  INFO {translate.py:348} - Completed translation of "org.jenkinsci.plugins.mesos.MesosCloud" @ "mesos@1.0.0" in the config file to the Kubernetes Cloud configuration
--------------------------------------------------
Copy the generated "<user_path>/mesosphere/dcos-migration/k8s.config.xml" to Jenkins master node on kubernetes using command :
kubectl cp <user_path>/mesosphere/dcos-migration/k8s.config.xml $(kubectl get pods --namespace jenkins -l=app.kubernetes.io/instance=jenkins --no-headers --output custom-columns=":metadata.name"):/var/jenkins_home/config.xml --namespace jenkins --container jenkins
--------------------------------------------------
Create the following ConfigMap that will be used to mount the JNLP configuration script for your jenkins agents:
kubectl apply -f ./jenkins/resources/configmap-jenkins-agent-3-35-5.yaml --namespace jenkins
--------------------------------------------------
```

Copy paste the commands from above output to create serviceaccount, role, rolebinding, values.yaml, and configmap.
Finally install the jenkins chart using helm v2 or helm v3 based on your environment.

Use `migrate update` command to update the jobs definitions by migrating them to kubernetes plugin supported definitions. Optionally, disable the jobs as desired. 

```
➜ python3 ./jenkins/scripts/main.py migrate update --disable-jobs
[2020-11-08 12:48:47,002]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/test
[2020-11-08 12:48:47,016]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/freeeform/job/hellofreeform
[2020-11-08 12:48:47,032]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/freeeform/job/rust-agent-build
[2020-11-08 12:48:47,048]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/Hello-world
[2020-11-08 12:48:47,065]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/pipeline-job
[2020-11-08 12:48:47,082]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/examples/job/simple-node-js-react-npm-app
[2020-11-08 12:48:47,100]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/Test-job-mvn-template
[2020-11-08 12:48:47,116]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/react-node-pipeline-job
[2020-11-08 12:48:47,134]  INFO {main.py:212} - Processed job <user_path>/mesosphere/dcos-migration/jenkins_home/job/maven-job-freestyle
[2020-11-08 12:48:47,134]  INFO {main.py:215} - Processed "9" jobs from "<user_path>/mesosphere/dcos-migration/jenkins_home/jobs"
```

Finally copy over the job defintions to jenkins master node using `migrate copy`.

```
➜ python3 ./jenkins/scripts/main.py migrate copy
kubectl exec jenkins-7f9c46d7f-mhk9g --namespace jenkins --container jenkins -- sh -c "mkdir -p /var/jenkins_home/jobs/"
kubectl --namespace jenkins --container jenkins cp <user_path>/mesosphere/dcos-migration/jenkins_home/jobs jenkins-7f9c46d7f-mhk9g:/var/jenkins_home
```

Hit Reload Configuration from Desk in Jenkins UI to make sure all the updates are reflected.
