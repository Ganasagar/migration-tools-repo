import logging as log
import os

from utils import run_cmd

# KUBERNETES CLI
KUBECTL = os.getenv("KUBECTL", "kubectl")
RESTORE_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../resources/dcos_cassandra_restore.sh")


def _generate_restore_cmd(instance: str, node_index: int, namespace: str, restore_params: dict) -> str:
    cmd = "/tmp/dcos_cassandra_restore.sh --instance {} --pod-index {} --namespace {} ".format(
        instance, node_index, namespace)
    cmd += "--bucket-name {} --snapshot {} --aws-region {} --aws-key {} --aws-secret {}".format(
        restore_params["S3_BUCKET_NAME"], restore_params["SNAPSHOT_NAME"], restore_params["AWS_REGION"],
        restore_params["AWS_ACCESS_KEY_ID"], restore_params["AWS_SECRET_ACCESS_KEY"])
    if "AWS_SESSION_TOKEN" in restore_params:
        cmd += " --aws-token {}".format(restore_params["AWS_SESSION_TOKEN"])
    return cmd


def restore_schema_and_data(namespace: str, instance: str, node_count: int, restore_params: dict):
    if not os.path.exists(RESTORE_SCRIPT):
        log.fatal("Missing Restore script {}".format(RESTORE_SCRIPT))
        return

    log.info("Validating Cassandra Instance is running correctly")
    run_cmd("{} kudo plan status --namespace={} --instance={}".format(KUBECTL, namespace, instance), check=True)

    for node_index in range(node_count):
        pod_name = instance + '-node-' + str(node_index)
        log.info("Restoring schema and data for pod {}".format(pod_name))

        log.info("Copying restore script to pod {}".format(pod_name))
        rc, _, _ = run_cmd("{} cp {} {}/{}:/tmp/".format(KUBECTL, RESTORE_SCRIPT, namespace, pod_name))
        if rc != 0:
            log.error("Failed to copy restore script.")
            return

        log.info("Running restore script in pod {}".format(pod_name))
        restore_cmd = _generate_restore_cmd(instance, node_index, namespace, restore_params)
        rc, _, _ = run_cmd("{} exec --namespace={} {} -c cassandra -- {}".format(KUBECTL, namespace, pod_name,
                                                                                 restore_cmd))
        if rc != 0:
            log.error("Failed to run restore script.")
            return
