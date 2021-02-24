.PHONY: mypy test setup shell ci docker

PYTHON_VERSION := $(shell cat .python-version)
VERSION := $(shell ./version)

# ---------------------------
# if we're already inside a pipenv shell, then we do not need to install anything. Assume the environment is already set up correctly
ifeq ($(PIPENV_ACTIVE), 1)
PREFIX=

setup shell:
	echo "Pipenv shell active; skipping install"

else
# if we're not in a pipenv shell, install pipenv if it isn't already, and then run pipenv install
PREFIX=python -m pipenv run

setup:
	python -m pipenv install -d

shell: setup
	python -m pipenv shell

endif
# ----------------------------

mypy: | setup
	$(PREFIX) mypy --strict --warn-unused-ignores src

test: | setup
	$(PREFIX) pytest tests/

ci: mypy test

docker:
	docker build --build-arg PYTHON_VERSION=$(PYTHON_VERSION) -t mesosphere/dcos-migration:${VERSION} .
