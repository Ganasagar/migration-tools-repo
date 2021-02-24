import logging as log
import json
import os
import subprocess
import sys


# DCOS CLI
DCOS = os.getenv("DCOS_CLI", "dcos")
MARATHON_JSON = "marathon_app.json"

# Constants
encoding = "utf-8"


def run_cmd(cmd: str, print_output: bool = False, check: bool = True, timeout_seconds: int = 300, print_cmd: bool = False) -> [int, str, str]:
    log.debug('Running command "{}"'.format(cmd, check))
    if print_cmd:
        print(cmd)
    stdout = ""
    stderr = ""
    try:
        result = subprocess.run(
            [cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            check=check,
            timeout=timeout_seconds,
        )

        if result.stdout:
            stdout = result.stdout.decode(encoding).strip()

        if result.stderr:
            stderr = result.stderr.decode(encoding).strip()

        if print_output and result.returncode != 0:
            log.info("Got exit code {} to command: {}".format(result.returncode, cmd))

        if print_output:
            if stdout:
                log.info("STDOUT:\n{}".format(stdout))
            if stderr:
                log.info("STDERR:\n{}".format(stderr))
        return result.returncode, stdout, stderr
    except subprocess.CalledProcessError as e:
        if e.stdout:
            stdout = e.stdout.decode(encoding).strip()
        if e.stderr:
            stderr = e.stderr.decode(encoding).strip()
        log.error("STDOUT:\n{}".format(stdout))
        log.error("STDERR:\n{}".format(stderr))
        if check:
            sys.exit(e.returncode)
        return e.returncode, stdout, stderr


def download_dcos_package(app_id: str, target_dir: str, versions: [str], use_existing_dir: bool) -> [str, str]:
    log.info("Validating DC/OS CLI is setup correctly")
    run_cmd("{} --version".format(DCOS), check=True)
    target_dir = os.path.abspath(target_dir)

    _, out, err = run_cmd("{} marathon app show {}".format(DCOS, app_id))
    if len(out) == 0:
        log.error("Empty output detected")
        return

    app = json.loads(out, encoding=encoding)
    os.makedirs(target_dir, exist_ok=True)
    if not use_existing_dir and len(os.listdir(target_dir)) != 0:
        log.fatal('Provided directory "{}" is not empty. Use an empty directory to prevent data corruption.'.format(target_dir))
    with open(os.path.join(target_dir, MARATHON_JSON), "w+") as f:
        f.write(out)
    DCOS_PACKAGE_NAME = app["labels"]["DCOS_PACKAGE_NAME"]
    if DCOS_PACKAGE_NAME != "jenkins":
        log.error('Cannot migrate "{}" package. Supported package is "jenkins"'.format(DCOS_PACKAGE_NAME))
        return
    DCOS_PACKAGE_VERSION = app["labels"]["DCOS_PACKAGE_VERSION"]
    if DCOS_PACKAGE_VERSION not in versions:
        log.error('Cannot migrate "{}" package : version "{}" not yet supported. Supported versions are {}'.format(
            DCOS_PACKAGE_NAME, DCOS_PACKAGE_VERSION, versions))
        return
    TASKS = app["tasks"]
    if len(TASKS) != 1:
        log.error("Expected tasks: 1, Found tasks: {}".format(len(TASKS)))
        return
    TASK_ID = TASKS[0]["id"]
    return DCOS_PACKAGE_VERSION, TASK_ID


def download_task_data(task_id: str, target_dir: str) -> str:
    log.info("Downloading config.xml")
    run_cmd("{} -v task download {} jenkins_home/config.xml --target-dir={}".format(DCOS, task_id, target_dir), check=True, print_cmd=True)
    log.info('Downloading jobs folder')
    run_cmd("{} task download {} jenkins_home/jobs --target-dir={}".format(DCOS, task_id, target_dir), check=False, print_cmd=True)
    return "{}/config.xml".format(target_dir)
