import os
from utils import colors

# KUBERNETES CLI
KUBECTL = os.getenv("KUBECTL", "kubectl")


def print_migration_instructions(namespace: str, instance: str, bootstrap_servers: str):
    separator = "--------------------------------------------------"

    KUDO_MIGRATION_CMD = """
    {kubectl} kudo update --instance={instance} --namespace={namespace} \\
    -p MIRROR_MAKER_ENABLED=true \\
    -p MIRROR_MAKER_TOPIC_WHITELIST=".*" \
    -p MIRROR_MAKER_EXTERNAL_BOOTSTRAP_SERVERS={bootstrap_servers} \\
    -p MIRROR_MAKER_EXTERNAL_CLUSTER_TYPE=SOURCE
    """
    # Issue commands for initiating the migration process
    print(separator)
    print(colors.BOLD + "Make sure the KUDO Kafka installation plan shows COMPLETE, before proceeding for migration." +
          colors.ENDC)
    print(separator)
    print(colors.OKGREEN + "Run the following command to start migration of your Kafka cluster {}".format(
        KUDO_MIGRATION_CMD.format(
            kubectl=KUBECTL, namespace=namespace, instance=instance, bootstrap_servers=bootstrap_servers)) +
          colors.ENDC)
