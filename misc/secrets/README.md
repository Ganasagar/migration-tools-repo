# DC/OS secrets migration tool

This guide walks through the various files and their role in performing a successful migration of secrets on DC/OS to secrets on Konvoy.

## Prerequisites

- `python3` installed in the environment
- DC/OS CLI `dcos` setup to talk to a DC/OS Cluster

### Overview 
At a higher level, migration can be seen as three steps:

1. Backup a path containing one or more DC/OS secrets.
2. Migrate the DC/OS secrets to a Kubernetes Secret resource definition.
3. Apply the Secret resource to add it to Kubernetes cluster.

## Commands

The command to export secrets from DC/OS to a file:

```
➜ python3 ./secrets/backup.py --help
usage: backup.py [-h] [--path PATH] [--output OUTPUT]
                 [--no-verify | --ca-file VERIFY]

Backup secrets from DC/OS secrets service.

optional arguments:
  -h, --help        show this help message and exit
  --path PATH       DC/OS secrets namespace to export (default: all secrets)
  --output OUTPUT   DC/OS secrets output file (default: stdout)
  --no-verify       do not verify connections to DC/OS (insecure)
  --ca-file VERIFY  specify a CA bundle file to verify connections to DC/OS
``` 

If `path` is specified, all secrets under that path are exported. If `path` is not specified, all secrets are exported.

The command to convert the DC/OS secrets file to a Kubernetes Secret resource file:

```
➜ python3 ./secrets/migrate.py --help
usage: migrate.py [-h] [--input INPUT] [--output OUTPUT]
                  [--namespace NAMESPACE] --name NAME

Migrate secrets from DC/OS to K8s.

optional arguments:
  -h, --help            show this help message and exit
  --input INPUT         DC/OS secrets file
  --output OUTPUT       K8s secrets file
  --namespace NAMESPACE
                        K8s secrets namespace
  --name NAME           K8s secrets name
``` 

The output file contains a single Kubernetes Secret definition containing all secrets from the DC/OS path.

The output file can be edited manually to change properties of the Secret resource, or to remove unwanted secrets.

This file can be used to create a Secret resource in Kubernetes, for example using the command:

```
➜ kubectl apply -f k8s-secret.yaml
```
