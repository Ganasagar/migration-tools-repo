#!/bin/bash

set -e -x

# Ensure we are in the directory containing this script
cd $(dirname "${BASH_SOURCE[0]}")

[ -d ./venv ] || virtualenv --python=$(which python3) ./venv

source ./venv/bin/activate

pip install --upgrade -r requirements.txt

# These tests require an installer (`dcos_generate_config.ee.sh`) and license
# file (`license.txt`) in this directory.
installer=${PWD}/dcos_generate_config.ee.sh
export DCOS_E2E_GENCONF_PATH=${installer}
export DCOS_E2E_TMP_DIR_PATH=/tmp
export DCOS_LICENSE=$(cat ${PWD}/license.txt)
export DCOS_E2E_LOG_DIR=/tmp/logs

PYTHONPATH=${PWD}/.. pytest "$@"
