import logging as log
import json
import os
import subprocess
import sys

from utils import encoding, remove_prefix, run_cmd

# DCOS CLI
DCOS = os.getenv("DCOS_CLI", "dcos")
MARATHON_JSON = "marathon_app.json"
CASSANDRA_ENV_JSON = "cassandra_env.json"


def _fetch_tasks_envs(app_id: str, task_count: int) -> dict:
    envs = {}
    for task in range(task_count):
        task_name = remove_prefix(app_id, '/').replace('/', '.') + "__node-{}-server__".format(task)
        log.info("Downloading configuration from task: {}".format(task_name))
        _, out, err = run_cmd("{} task exec {} bash -c 'env'".format(DCOS, task_name))
        for env in out.split('\n'):
            key, value = env.split('=')
            if key not in envs:
                envs[key] = [value]
            else:
                envs[key].append(value)
        _, out, err = run_cmd("{} task exec {} bash -c 'cat $MESOS_SANDBOX/new_user_password'".format(DCOS, task_name))
        envs["NEW_USER_PASSWORD"] = out
    return envs


def _sanitize_and_merge_envs(app_env: dict, task_env: dict) -> dict:
    envs = {}
    for (k, v) in app_env.items():
        envs[remove_prefix(k, "TASKCFG_ALL_")] = v
    for (k, v) in task_env.items():
        if v.count(v[0]) == len(v):
            v = v[0]
        envs[remove_prefix(k, "TASKCFG_ALL_")] = v
    return envs


def _generate_backup_cmd(app_id: str, backup_params: dict) -> str:
    cmd = "cassandra --name={} plan start backup-s3".format(app_id)
    for param_key in backup_params:
        cmd += ' -p "{}={}"'.format(param_key, backup_params[param_key])
    return cmd


def print_backup_instructions(app_id: str, backup_cmd: str):
    separator = "--------------------------------------------------"
    print("\n{}".format(separator))
    print("Run following command to trigger the Schema and Data backup:")
    print("\n{} {}".format(DCOS, backup_cmd))
    print(separator)
    print("\nRun following command to check the backup status:")
    print("\n{} cassandra --name={} plan status backup-s3".format(DCOS, app_id))
    print("\nNote: Make sure backup plan is completed to go forward.")
    print(separator)


def download_dcos_package(app_id: str, target_dir: str, version: str):
    log.info("Validating DC/OS CLI is setup correctly")
    run_cmd("{} --version".format(DCOS), check=True)
    log.info("Validating DC/OS Cassandra Service and CLI are setup correctly")
    run_cmd("{} cassandra plan status deploy".format(DCOS), check=True)
    target_dir = os.path.abspath(target_dir)

    _, out, err = run_cmd("{} marathon app show {}".format(DCOS, app_id))
    if len(out) == 0:
        log.error("Empty output detected")
        return

    app = json.loads(out, encoding=encoding)
    os.makedirs(target_dir, exist_ok=True)
    if len(os.listdir(target_dir)) != 0:
        log.fatal('Provided directory "{}" is not empty. Use an empty directory to prevent data corruption.'.format(
            target_dir))
    with open(os.path.join(target_dir, MARATHON_JSON), "w+") as f:
        f.write(out)
    DCOS_PACKAGE_NAME = app["labels"]["DCOS_PACKAGE_NAME"]
    if DCOS_PACKAGE_NAME != "cassandra":
        log.error('Cannot migrate "{}" package. Supported package is "cassandra"'.format(DCOS_PACKAGE_NAME))
        return
    DCOS_PACKAGE_VERSION = app["labels"]["DCOS_PACKAGE_VERSION"]
    if DCOS_PACKAGE_VERSION != version:
        log.error('Cannot migrate "{}" package : version "{}". Provided version "{}" is not found.'.format(
            DCOS_PACKAGE_NAME, DCOS_PACKAGE_VERSION, version))
        return

    if len(app["tasks"]) == 0:
        log.error("No Task Found")
        return

    tasks_envs = _fetch_tasks_envs(app_id, int(app["env"]["NODES"]))
    app_envs = _sanitize_and_merge_envs(app["env"], tasks_envs)

    with open(os.path.join(target_dir, CASSANDRA_ENV_JSON), "w+") as f:
        json.dump(app_envs, f)


def download_task_data_on_s3(app_id: str, backup_params: dict):
    log.info("Generating command for Schema and Data Backup plan")
    backup_cmd = _generate_backup_cmd(app_id, backup_params)
    print_backup_instructions(app_id, backup_cmd)
