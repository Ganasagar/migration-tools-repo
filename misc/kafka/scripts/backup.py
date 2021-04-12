import logging as log
import json
import os
from utils import encoding, remove_prefix, run_cmd

# DCOS CLI
DCOS = os.getenv("DCOS_CLI", "dcos")
MARATHON_JSON = "marathon_app.json"
KAFKA_ENV_JSON = "kafka_env.json"


def _fetch_tasks_envs(app_id: str, task_count: int) -> dict:
    """Pulls task configuration"""
    envs = {}
    for task in range(task_count):
        task_name = remove_prefix(app_id, "/").replace("/", ".") + "__kafka-{}-broker__".format(task)
        log.info("Downloading configuration from task: {}".format(task_name))
        _, out, err = run_cmd("{} task exec {} bash -c 'env'".format(DCOS, task_name))
        for env in out.split("\n"):
            key, value = env.split("=")
            if key not in envs:
                envs[key] = [value]
            else:
                envs[key].append(value)
    return envs


def _sanitize_and_merge_envs(app_env: dict, task_env: dict) -> dict:
    """Cleans the env vars by trimming DCOS task prefixes"""
    envs = {}
    for (k, v) in app_env.items():
        envs[remove_prefix(k, "TASKCFG_ALL_")] = v
    for (k, v) in task_env.items():
        if v.count(v[0]) == len(v):
            v = v[0]
        envs[remove_prefix(k, "TASKCFG_ALL_")] = v
    return envs


def download_dcos_package(app_id: str, target_dir: str, version: str):
    """Downloads the marathon definition of the deployed kafka service."""
    log.info("Validating DC/OS CLI is setup correctly")
    run_cmd("{} --version".format(DCOS), check=True)
    log.info("Validating DC/OS Kafka Service and CLI are setup correctly")
    # Check the deployment status for both Apache and Confluent Kafka using kafka cli
    run_cmd("{} kafka --name={} plan status deploy".format(DCOS, app_id), check=True)
    target_dir = os.path.abspath(target_dir)
    # Get the marathon configuration of the kafka service
    _, out, err = run_cmd("{} marathon app show {}".format(DCOS, app_id))
    if len(out) == 0:
        log.error("Empty output detected.")
        return

    app = json.loads(out, encoding=encoding)
    os.makedirs(target_dir, exist_ok=True)
    if len(os.listdir(target_dir)) != 0:
        log.fatal('Provided directory "{}" is not empty. Use an empty directory to prevent data corruption.'.format(
            target_dir))
    with open(os.path.join(target_dir, MARATHON_JSON), "w+") as f:
        f.write(out)
    DCOS_PACKAGE_FRAMEWORK_NAME = app["labels"]["DCOS_PACKAGE_FRAMEWORK_NAME"]
    if DCOS_PACKAGE_FRAMEWORK_NAME not in ["kafka", "confluent-kafka"]:
        log.error('Cannot migrate "{}" package. Supported packages are "Kafka and Confluent-Kafka"'.format(
            DCOS_PACKAGE_FRAMEWORK_NAME))
        return
    DCOS_PACKAGE_VERSION = app["labels"]["DCOS_PACKAGE_VERSION"]
    # TODO: @rishabh96b - Uncomment below snippet if migration faces version dependent issues.
    # if DCOS_PACKAGE_VERSION != version:
    #     log.error('Cannot migrate "{}" package : version "{}". Provided version "{}" is not found.'.format(
    #         DCOS_PACKAGE_FRAMEWORK_NAME, DCOS_PACKAGE_VERSION, version))
    #     return

    if len(app["tasks"]) == 0:
        log.error("No Task Found")
        return

    tasks_envs = _fetch_tasks_envs(app_id, int(app["env"]["BROKER_COUNT"]))
    app_envs = _sanitize_and_merge_envs(app["env"], tasks_envs)

    with open(os.path.join(target_dir, KAFKA_ENV_JSON), "w+") as f:
        json.dump(app_envs, f)
