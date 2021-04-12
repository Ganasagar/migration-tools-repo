# Cassandra Migration Tool

This guide walks through the various files and their role in performing a successful migration of Cassandra on DC/OS to Cassandra on DKP.

## Prerequisites

- `python3` installed in the environment
- DC/OS CLI `dcos` setup to talk to a DC/OS Cluster
- DC/OS Cassandra CLI `dcos package install cassandra --cli` setup to talk to Cassandra service.
- AWS Credentials for S3 backups
- Kubernetes CLI `kubectl` setup to talk to a konvoy cluster
- Kudo CLI `kubectl kudo` setup to install operators
- Make sure Kudo is initiated `kubectl kudo init`
- Basic knowledge of kubernetes, kudo and Cassandra.
- Script is tested to work in Linux based environments.


## Commands

Python file located at `scripts/main.py` is the main entrypoint for the tooling used to migrate cassandra. The help menu describes the steps involved in migration:

```
➜ python3 ./cassandra/scripts/main.py --help

usage: main.py [-h] [--version] {backup,install,migrate} ...

positional arguments:
  {backup,install,migrate}
                        sub-commands available
    backup              Backup the DC/OS package configurations and data
    install             Translate the DC/OS based configs to KUDO based
                        configs and print install instructions.
    migrate             Restore the Schema and Data from the backup of DC/OS
                        Cassandra to KUDO Cassandra

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
``` 

### Overview 
At a higher level, migration can be seen as three steps:

1. Backup the DC/OS Cassandra configurations locally, as well as support backup of metadata and data on S3.
2. Install Cassandra on DKP by translating the above downloaded configuration and adding other customization.
3. Optional, If any schema and data backup available on S3, restore it in Cassandra on DKP.

These steps are explained in following steps:

### `1.backup`

By providing a service name or app-id (defaults to `/cassandra`), all the configurations can be downloaded to local file system and data can be backed up to S3.

```
➜ python3 ./cassandra/scripts/main.py backup --help

usage: main.py backup [-h] [-t TARGET_DIR] [--app-id APP_ID]
                      [--only-conf ONLY_CONF] [--app-version APP_VERSION]
                      [--snapshot-name SNAPSHOT_NAME]
                      [--bucket-name BUCKET_NAME] [--keyspaces KEYSPACES]
                      [--aws-key AWS_KEY] [--aws-secret AWS_SECRET]
                      [--aws-session-id AWS_SESSION_ID]
                      [--aws-session-token AWS_SESSION_TOKEN]
                      [--aws-region AWS_REGION] [--https-proxy HTTPS_PROXY]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        Folder to hold configuration of running DC/OS
                        Cassandra service (defaults to ./cassandra_home)
  --app-id APP_ID       Service Name (defaults to cassandra)
  --only-conf ONLY_CONF
                        Set True if only service configuration is required, no
                        data backup (defaults to False)
  --app-version APP_VERSION
                        Service Version (defaults to 2.10.0-3.11.6)
  --snapshot-name SNAPSHOT_NAME
                        Snapshot or Backup Name (required, not applicable if
                        --only-conf=True)
  --bucket-name BUCKET_NAME
                        S3 Bucket Name, without s3:// prefix (required, not
                        applicable if --only-conf=True)
  --keyspaces KEYSPACES
                        Comma separated list of keyspace names for the Backup
  --aws-key AWS_KEY     AWS Access Key ID (required, not applicable if --only-
                        conf=True)
  --aws-secret AWS_SECRET
                        AWS Secret Access Key (required, not applicable if
                        --only-conf=True)
  --aws-session-id AWS_SESSION_ID
                        AWS Session ID
  --aws-session-token AWS_SESSION_TOKEN
                        AWS Session Token
  --aws-region AWS_REGION
                        AWS Region (defautls to us-west-2)
  --https-proxy HTTPS_PROXY
                        HTTPs Proxy
```

`TARGET_DIR` defaults to `$(pwd)/cassandra_home`. `--only-conf` option can be set to `true` if you want to avoid any kind of data backup and only wants to migrate cassandra service.

If `--only-conf` option is not set to `true`, there are following options that would be required for successful S3 Schema and Data backup:
`--snapshot-name`, `--bucket-name`, `--aws-key` and `--aws-secret`


### `2.install`

The `install` command generates a `TARGET_FILE` (that defaults to `$(pwd)/cassandra_home/params.yml` ) and prints instructions on how to use it to install in Cassandra on DKP. Other parameters such as `namespace` and `instance` have sensible defaults in accordance with the upstream kudo operator definition but can be customized.

```
➜ python3 ./cassandra/scripts/main.py install --help

usage: main.py install [-h] [-t TARGET_DIR] [-c CONFIG_FILE] [-f TARGET_FILE]
                       [--namespace NAMESPACE] [--instance INSTANCE]
                       [--operator-version OPERATOR_VERSION]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        Folder to hold configuration of running DC/OS
                        Cassandra service (defaults to ./cassandra_home)
  -c CONFIG_FILE, --config-file CONFIG_FILE
                        Path of the cassandra env file generated by backup
                        command. (defaults to
                        ./cassandra_home/cassandra_env.json)
  -f TARGET_FILE, --target-file TARGET_FILE
                        Path of the target params file (defaults to
                        ./cassandra_home/params.yml)
  --namespace NAMESPACE
                        Namespace of the cassandra pods (defaults to default)
  --instance INSTANCE   Name of the Cassandra Kudo installation (defaults to
                        cassandra-instance)
  --operator-version OPERATOR_VERSION
                        Kudo Cassandra version (defaults to 0.1.2)
```

`TARGET_DIR` is used to store generated `cassandra-auth.yaml` file in case of Password Authenticator set in Cassandra on DC/OS. Install command will also check if TLS is enabled, it prints instructions to create TLS secret required for Cassandra on DKP.


### `3.migrate`

The `migrate` command is to be used when you have data backup taken in S3 from Cassandra on DC/OS. This command will restore the data backup taken from Cassandra on DC/OS to Cassandra on DKP.

```
➜ python3 ./cassandra/scripts/main.py migrate --help

usage: main.py migrate [-h] [--namespace NAMESPACE] [--instance INSTANCE]
                       [--count COUNT] --snapshot-name SNAPSHOT_NAME
                       --bucket-name BUCKET_NAME --aws-key AWS_KEY
                       --aws-secret AWS_SECRET
                       [--aws-session-token AWS_SESSION_TOKEN]
                       [--aws-region AWS_REGION]

optional arguments:
  -h, --help            show this help message and exit
  --namespace NAMESPACE
                        Namespace of the cassandra pods (defaults to default)
  --instance INSTANCE   Name of the Cassandra Kudo installation (defaults to
                        cassandra-instance)
  --count COUNT         Count of the cassandra node (defaults to 3)
  --snapshot-name SNAPSHOT_NAME
                        Snapshot or Backup Name
  --bucket-name BUCKET_NAME
                        S3 Bucket Name, without s3:// prefix
  --aws-key AWS_KEY     AWS Access Key ID
  --aws-secret AWS_SECRET
                        AWS Secret Access Key
  --aws-session-token AWS_SESSION_TOKEN
                        AWS Session Token
  --aws-region AWS_REGION
                        AWS Region (defautls to us-west-2)
```

The `--count` option should have value that match with the number of node for which backup has been taken.

### Sample Output

Following is a sample output of running through all the commands. Note that all the flags provided are using their default values.

`backup` the Cassandra running on DC/OS with instance id `/cassandra` to a folder named `cassandra_home`

```
➜ python3 ./cassandra/scripts/main.py backup \
    --app-id=cassandra --target-dir=$(pwd)/cassandra_home \
    --app-version=2.10.0-3.11.6 --snapshot-name=cassandra_backup \
    --bucket-name=mybucket --aws-key=ABCDEFGHIJKLMNOPQRSTUVWXYZ \
    --aws-secret=AbC/+123/xyZ

[2020-11-20 08:30:43,219]  INFO {main.py:49} - Downloading DC/OS package with app id cassandra of version 2.10.0-3.11.6 into target directory <user_path>/dcos-migration/cassandra_home
[2020-11-20 08:30:43,219]  INFO {backup.py:61} - Validating DC/OS CLI is setup correctly
[2020-11-20 08:30:43,219]  INFO {backup.py:63} - Validating DC/OS Cassandra Service and CLI are setup correctly
[2020-11-20 08:30:43,219]  INFO {backup.py:19} - Downloading configuration from task: cassandra__node-0-server__
[2020-11-20 08:30:43,219]  INFO {backup.py:19} - Downloading configuration from task: cassandra__node-1-server__
[2020-11-20 08:30:43,219]  INFO {backup.py:19} - Downloading configuration from task: cassandra__node-2-server__
[2020-11-20 08:30:43,219]  INFO {backup.py:100} - Generating command for Schema and Data Backup plan

--------------------------------------------------
Run following command to trigger the Schema and Data backup:

dcos cassandra --name=cassandra plan start backup-s3 -p "SNAPSHOT_NAME=cassandra_backup" -p "S3_BUCKET_NAME=mybucket" -p "AWS_ACCESS_KEY_ID=ABCDEFGHIJKLMNOPQRSTUVWXYZ" -p "AWS_SECRET_ACCESS_KEY=AbC/+123/xyZ" -p "AWS_REGION=us-west-2"
--------------------------------------------------

Run following command to check the backup status:

dcos cassandra --name=cassandra plan status backup-s3

Note: Make sure backup plan is completed to go forward.
--------------------------------------------------
```

Backup plan status should look as follows:

```
backup-s3 (serial strategy) (COMPLETE)
├─ backup-schema (serial strategy) (COMPLETE)
│  ├─ node-0:[backup-schema] (COMPLETE)
│  ├─ node-1:[backup-schema] (COMPLETE)
│  └─ node-2:[backup-schema] (COMPLETE)
├─ create-snapshots (dependency strategy) (COMPLETE)
│  ├─ node-0:[snapshot] (COMPLETE)
│  ├─ node-1:[snapshot] (COMPLETE)
│  └─ node-2:[snapshot] (COMPLETE)
├─ upload-backups (serial strategy) (COMPLETE)
│  ├─ node-0:[upload-s3] (COMPLETE)
│  ├─ node-1:[upload-s3] (COMPLETE)
│  └─ node-2:[upload-s3] (COMPLETE)
└─ cleanup-snapshots (serial strategy) (COMPLETE)
   ├─ node-0:[cleanup-snapshot] (COMPLETE)
   ├─ node-1:[cleanup-snapshot] (COMPLETE)
   └─ node-2:[cleanup-snapshot] (COMPLETE)
```

`translate`

```
➜ python3 ./cassandra/scripts/main.py install -c $(pwd)/cassandra_home/cassandra_env.json -f $(pwd)/cassandra_home/params.yml --namespace default --instance cassandra-instance --operator-version 0.1.2

[2020-11-20 08:40:31,631]  INFO {main.py:57} - Translating Mesos configurations to K8s configurations
[2020-11-20 08:40:31,632]  INFO {translate.py:76} - Using "<user_path>/dcos-migration/cassandra_home/cassandra_env.json" file to migrate to kubernetes configuration at "<user_path>/dcos-migration/cassandra_home/params.yml"

--------------------------------------------------
WARNING: ALL THE PARAMETERS ARE GENERATED AS PER THE DCOS VERSION OF THE SERVICE, IT MIGHT NOT BE THE BEST FOR K8s.
SO BEFORE INSTALLING THE SERVICE PLEASE OPEN A TARGET FILE (<user-path>/dcos-migration/cassandra_home/params.yml) AND MODIFY VALUES AS PER THE AVAILABILITY ON THE K8s CLUSTER.
SPECIALLY VALUES OF THESE FIELDS SHOULD BE ADJUSTED AS PER THE CLUSTER:
NODE_COUNT
NODE_CPU_MC
NODE_CPU_LIMIT_MC
NODE_MEM_MIB
NODE_MEM_LIMIT_MIB
NODE_DISK_SIZE_GIB
NODE_TOPOLOGY
EXTERNAL_SEED_NODES
OTC_COALESCING_STRATEGY - value should be one of these [disabled fixed movingaverage timehorizon]
ENDPOINT_SNITCH - if GossipingPropertyFileSnitch not working, use SimpleSnitch
TLS_SECRET_NAME - Only relavent if TLS is enabled
AUTHENTICATION_SECRET_NAME - Only relavent if AUTHENTICATOR is set to PasswordAuthenticator

--------------------------------------------------
Run the following command to install Cassandra on K8s: 
kubectl kudo install \
    --namespace default \
    --instance cassandra-instance \
    --parameter-file <user_path>/dcos-migration/cassandra_home/params.yml \
    --operator-version 0.1.2 \
    cassandra

--------------------------------------------------
Run the following command to check the status: 
kubectl kudo plan status \
    --namespace default \
    --instance=cassandra-instance

--------------------------------------------------
Make sure plan shows COMPELTE, before proceeding further.
--------------------------------------------------
```

Modify `<user-path>/dcos-migration/cassandra_home/params.yml` file as per your requirement and Copy paste the commands from the above output to install the service.

`migrate`

```
➜ python3 ./cassandra/scripts/main.py migrate \
    --namespace=default --instance=cassandra-instance \
    --count=3 --snapshot-name=cassandra_backup \
    --bucket-name=mybucket --aws-key=ABCDEFGHIJKLMNOPQRSTUVWXYZ \
    --aws-secret=AbC/+123/xyZ

[2020-12-08 17:35:17,721]  INFO {main.py:65} - Restoring Schema and Data to K8s Cassandra
[2020-12-08 17:35:17,721]  INFO {restore.py:32} - Validating Cassandra Instance is running correctly
[2020-12-08 17:35:17,721]  INFO {restore.py:39} - Restoring schema and data for pod cassandra-instance-node-0
[2020-12-08 17:35:17,721]  INFO {restore.py:41} - Copying restore script to pod cassandra-instance-node-0
[2020-12-08 17:35:17,721]  INFO {restore.py:48} - Running restore script in pod cassandra-instance-node-0
[2020-12-08 17:35:17,721]  INFO {restore.py:39} - Restoring schema and data for pod cassandra-instance-node-1
[2020-12-08 17:35:17,721]  INFO {restore.py:41} - Copying restore script to pod cassandra-instance-node-1
[2020-12-08 17:35:17,721]  INFO {restore.py:48} - Running restore script in pod cassandra-instance-node-1
[2020-12-08 17:35:17,721]  INFO {restore.py:39} - Restoring schema and data for pod cassandra-instance-node-2
[2020-12-08 17:35:17,721]  INFO {restore.py:41} - Copying restore script to pod cassandra-instance-node-2
[2020-12-08 17:35:17,721]  INFO {restore.py:48} - Running restore script in pod cassandra-instance-node-2
```
