
test: integration-test

# Integration tests require a DC/OS installer and license in the `tests` directory
integration-test:
	cd tests; ./run-tests.sh -v
