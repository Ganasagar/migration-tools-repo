import math
import os
import json
import logging as log
from pprint import pprint
from utils import colors

# KUBERNETES CLI
KUBECTL = os.getenv("KUBECTL", "kubectl")

WARNING = """
WARNING: ALL THE PARAMETERS ARE GENERATED AS PER THE DCOS VERSION OF THE SERVICE, IT MIGHT NOT BE THE BEST FOR K8s.
SO BEFORE INSTALLING THE SERVICE PLEASE OPEN A TARGET FILE ({}) AND MODIFY VALUES AS PER THE AVAILABILITY ON THE K8s CLUSTER.
SPECIALLY VALUES OF THESE FIELDS SHOULD BE ADJUSTED AS PER THE CLUSTER:
BROKER_COUNT
BROKER_CPUS
BROKER_MEM
BROKER_PORT
DISK_SIZE
"""


def print_instructions_zk(namespace: str, instance: str, target_file: str, version: str):
    separator = "--------------------------------------------------"

    KUDO_CMD = """
{kubectl} kudo install \\
    --namespace {namespace} \\
    --instance {instance} \\
    zookeeper
"""
    KUDO_STATUS_CMD = """
{kubectl} kudo plan status \\
    --namespace {namespace} \\
    --instance {instance}
"""
    print(separator)
    print(colors.HEADER + "Install KUDO Zookeeper" + colors.ENDC)
    print(separator)
    print(colors.OKGREEN + "Run the following command to install KUDO Zookeeper on DKP: {}".format(
        KUDO_CMD.format(kubectl=KUBECTL, namespace=namespace, instance=instance)) + colors.ENDC)
    print(separator)
    print(colors.OKGREEN + "Run the following command to check the status: {}".format(
        KUDO_STATUS_CMD.format(kubectl=KUBECTL, namespace=namespace, instance=instance)) + colors.ENDC)
    print(separator)
    print(colors.BOLD + "Make sure plan shows COMPELTE, before proceeding further." + colors.ENDC)
    print(separator)


def print_instructions_kafka(namespace: str, instance: str, target_file: str, version: str):
    separator = "--------------------------------------------------"

    KUDO_CMD = """
{kubectl} kudo install \\
    --namespace {namespace} \\
    --instance {instance} \\
    --parameter-file {target_file} \\
    --operator-version {version} \\
    kafka
"""
    KUDO_STATUS_CMD = """
{kubectl} kudo plan status \\
    --namespace {namespace} \\
    --instance {instance}
"""
    print("\n")
    print(separator)
    print(colors.HEADER + "Install KUDO Kafka" + colors.ENDC)
    print(separator)
    print(colors.WARNING + WARNING.format(target_file) + colors.ENDC)
    print(separator)
    print(colors.OKGREEN + "Run the following command to install KUDO Kafka on DKP: {}".format(
        KUDO_CMD.format(
            kubectl=KUBECTL,
            namespace=namespace,
            instance=instance,
            target_file=target_file,
            version=version,
        )) + colors.ENDC)
    print(separator)

    print(colors.OKGREEN + "Run the following command to check the status: {}".format(
        KUDO_STATUS_CMD.format(kubectl=KUBECTL, namespace=namespace, instance=instance)) + colors.ENDC)
    print(separator)
    print(colors.BOLD + "Make sure plan shows COMPELTE, before proceeding further." + colors.ENDC)
    print(separator)


def translate_mesos_to_k8s(src_file: str, target_file: str) -> bool:
    log.info(f'Using "{src_file}" file to migrate to kubernetes configuration at "{target_file}"')

    tmpl_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../resources/params.yaml.tmpl")

    if not os.path.exists(src_file):
        log.error("Mesos configuration file {} does not exists!".format(src_file))
        return False

    with open(src_file, "r") as f:
        src_envs = json.load(f)

    if not os.path.exists(tmpl_file):
        log.fatal("Missing Template File {}".format(tmpl_file))
        return False

    with open(tmpl_file, "r") as f:
        tmpl_lines = f.readlines()

    # Add zookeeper URI
    src_envs[
        "KAFKA_ZOOKEEPER_URI"] = "zookeeper-instance-zookeeper-0.zookeeper-instance-hs:2181,zookeeper-instance-zookeeper-1.zookeeper-instance-hs:2181,zookeeper-instance-zookeeper-2.zookeeper-instance-hs:2181"
    # Convert Disk Size from MB to GiB
    src_envs["BROKER_DISK_SIZE"] = (str(math.ceil(float(src_envs["BROKER_DISK_SIZE"]) / 1000)) + "Gi")

    # Round of the value of CPU
    src_envs["BROKER_CPUS"] = (str(math.ceil(float(src_envs["BROKER_CPUS"]) * 1000)) + "m")

    # Convert Broker Memory from MB to GiB
    src_envs["BROKER_MEM"] = str(math.ceil(float(src_envs["BROKER_MEM"]) / 1024)) + "Gi"

    # Change default Broker Port to 9093
    src_envs["BROKER_PORT"] = "9093"

    with open(target_file, "w") as f:
        for tmpl in tmpl_lines:
            tmpl_key, tmpl_value = tmpl.split(":")
            tmpl_value = tmpl_value.strip()
            if tmpl_value in src_envs and len(src_envs[tmpl_value]) > 0:
                f.write(tmpl_key + ': "' + src_envs[tmpl_value] + '"\n')
    return True
