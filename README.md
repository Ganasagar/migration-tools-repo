# dcos_migrate
Backup and Migrate DC/OS workloads to DKP


## Setup

This tool uses Python 3.8.x and pipenv to manage dependencies.

### Install Python 3.8.x

To begin, you should install `python` `3.8.x` using the preferred method for your operating system. [pyenv](https://github.com/pyenv/pyenv) is recommended.

If using `pyenv`, run `pyenv install $(cat .python-version)` to install the version of Python targetted by `dcos-migration`. Also, be sure to configure your shell environment so that the correct version of python is automatically selected.

### Pipenv

Install `pipenv` via `pip`:

```
pip install pipenv
```

And then, install the dependencies:

```
python -m pipenv install
```

If you plan to run the unit tests, instruct `pipenv` to also install development dependencies:

```
python -m pipenv install -d
```

## Running

First, you'll want to enter a `pipenv` shell; this is easily done via the Makefile (which will also install the dependencies as needed):

```
make shell
```

This will select the virtual environment, configure the environment variables and activate all dependencies used by `dcos-migrate`.

At the moment only a full backup and migrate run is supported:
`python ./src/dcos_migrate.py`

This will create a sub-folder `dcos-migrate` in the current working directory. It contains a `backup` folder with a complete backup of all workloads. And a `migrate` folder.

## Build docker container

To build the docker container, you need Docker installed. Docker v20 or later is recommended.

Use the Makefile to build the docker container:

```
make docker
```

The docker image is tagged with the current source repository version. You'll see the image name of the output of the previous command.

## Run with docker

Get the latest version

```
docker pull mesosphere/dcos-migration:latest
```

... or, build it locally:

```
make docker
```

### Run using your local DC/OS config

(be sure to use `mesosphere/dcos-migration:$(./version)` if you built locally)

```
docker run -v"${HOME}/.dcos:/root/.dcos"  mesosphere/dcos-migration:latest

docker run -v"${HOME}/.dcos:/root/.dcos"  mesosphere/dcos-migration:latest dcos-migrate -h
```

### Run using environment variables
**WIP**
```
docker run -e"DCOS_CLUSTER_"  mesosphere/dcos-migration:latest
```

## Migrated Manifests

This tool creates manifest plugin based for different DC/OS workloads.

### cluster
Cluster manifest is not really meant to be used. Its a configmap containing DC/OS cluster properties. Its annotations being used by other plugins to annotate workloads with DC/OS related properties like `cluster-id` oder the cluster name.

### secrets
This is a 1:1 migration of DC/OS secrets for each secret we create a Manifest with a Kubernetes secret containing exactly 1 secret.

As DC/OS didn't support combining multiple secret key-value-pairs into a single Secret the result might not be best practice on K8s. You can just simply combine the `data` part of a secret and create your own one.

### metronome

### Marathon
#### Placement constraints migration
Equality constraints (`IS` and `LIKE` with a non-regex value) are converted into
nodeSelector specifying the same label. Special fields `@region` and `@zone` are
substituted by the well-known K8s labels `topology.kubernetes.io/region` and
`topology.kubernetes.io/zone` accordingly. The `hostname` field in equality
constraints is substituted by a custom label `dcos.io/former-dcos-hostname`.
For example, an app with constraints
```
["rack", "LIKE", "insecure"],
["hostname", "IS", "dcos-123.example.com"],
["@zone", "IS", "antarctic-1"]
```
will be converted into
```
nodeSelector:
  rack: insecure
  dcos.io/former-dcos-hostname: dcos-123.example.com
  topology.kubernetes.io/zone: antarctic-1
```

The `UNIQUE` constraint on hostname is converted into pod anti-affinity to the
pods with the same selector label as the deployement using the
`kubernetes.io/hostname` topology domain.

Behaviors of `MAX_PER` and also of `UNIQUE` constraint on fields other than
hostname are **approximated** via `topologySpreadConstraints`. For example,
`["rack", "MAX_PER", 32]` will be converted into
```
spec:
  topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: rack
    whenUnsatisfiable: DoNotSchedule
    labelSelector: <same as the one used for the pods of generated deployment>
```
Note that behaviour on addition of new topology domain can be different
from the one of `MAX_PER`. In the example above, if an app has 33 replicas
and there exists only one value of the label "rack", all 33 pods will be
successfully scheduled. After that, if a node with a different value of "rack"
is added, all 33 pods will stay on the nodes with the first value of the label.
Pods will be spread evenly between the old and the new "rack" values only after
redeployment.

Other constraints (`GROUP_BY`, `UNLIKE`, `LIKE` with a non-trivial regex) are
ignored with a warning.

**NOTE**: Migration code is not assigning any labels to Kubernetes cluster
nodes. The user must review the labels used in the migrated deployments
and set them on the nodes on their own.

### packages

#### jenkins


## Testing

You can easily run the following to run the typechecker, and to run all of the unit tests:


```
make mypy test
```

If you'd like to run a single unit test, you can both install dev-dependencies and open up a `pipenv` shell with:

```
make shell
```

Then, inside of the shell, you can run a single unit test. As an for example:

```
pytest tests/test_marathon/test_app_transtalor -k env
```
