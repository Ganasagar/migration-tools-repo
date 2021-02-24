# Marathon Apps to Kubernetes YAML definition

This tool converts a JSON file containing Marathon app definitions (as obtained from the `/v2/apps` Marathon endpoint) to a Kubernetes YAML definition.

The tool uses pipenv to manage dependencies. To install dependencies using pipenv, execute this:

```
python -m pipenv install
```

Then, to execute it, run a command as follows:

```
python -m pipenv run ./migrate.py translate --path test/resources/hello.json --default-image busybox
```

The Kubernetes YAML is written to STDOUT.

# Commandline options

Please see the `--help` screen for a description of options the script supports.

```
python -m pipenv run ./migrate.py translate --help
```

# Running tests

Tests should be run from the root folder. To run the tests, it is recommended to use pipenv shell, first:

```
python -m pipenv shell
```

Then, from the `marathon` folder (the one containing this README), run:

```
pytest
```
