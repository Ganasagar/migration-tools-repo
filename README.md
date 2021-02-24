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

### marathon


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
