.PHONY: mypy test setup shell ci docker help

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


.Pipfile.installed: Pipfile Pipfile.lock
	python -m pipenv install -d
	touch $@


setup: .Pipfile.installed ## Install pipenv runtime dependencies and development dependencies

shell: setup ## Launch a shell with pipenv environment configured. Speeds up invocation of subsequent make invocations.
	python -m pipenv shell

endif
# ----------------------------

mypy: | setup ## Run the mypy linter
	$(PREFIX) mypy --strict --warn-unused-ignores src

test: | setup ## Run the unit tests
	$(PREFIX) pytest tests/

ci-check-clean:
	bin/ci-check-commit

ci: format mypy test ci-check-clean ## Run both mypy and unit tests

docker: ## Build a docker image
	docker build --build-arg PYTHON_VERSION=$(PYTHON_VERSION) -t mesosphere/dcos-migration:${VERSION} .

format: | setup ## Format all python code in misc/, src/ and tests/
	$(PREFIX) yapf -p --recursive misc src tests --in-place

# https://www.client9.com/self-documenting-makefiles/
help:
	@awk -F ':|##' '/^[^\t].+?:.*?##/ {\
	printf "\033[36m%-30s\033[0m %s\n", $$1, $$NF \
	        }' Makefile
.DEFAULT_GOAL=help
