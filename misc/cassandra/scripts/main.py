import argparse
import contextlib
import logging as log
import os
import shutil
import sys

import backup
import translate
import restore


def parse_backup_restore_params(args) -> dict:
    parsed_params = {}

    if len(args.snapshot_name) == 0:
        log.error("Missing value of --snapshot-name")
        exit(1)
    if len(args.bucket_name) == 0:
        log.error("Missing value of --bucket-name")
        exit(1)
    if len(args.aws_key) == 0:
        log.error("Missing value of --aws-key")
        exit(1)
    if len(args.aws_secret) == 0:
        log.error("Missing value of --aws-secret")
        exit(1)

    parsed_params["SNAPSHOT_NAME"] = args.snapshot_name
    parsed_params["S3_BUCKET_NAME"] = args.bucket_name
    parsed_params["AWS_ACCESS_KEY_ID"] = args.aws_key
    parsed_params["AWS_SECRET_ACCESS_KEY"] = args.aws_secret
    parsed_params["AWS_REGION"] = args.aws_region

    if hasattr(args, 'https_proxy') and len(args.https_proxy) != 0:
        parsed_params["HTTPS_PROXY"] = args.https_proxy
    if hasattr(args, 'aws_session_id') and len(args.aws_session_id) != 0:
        parsed_params["AWS_SESSION_ID"] = args.aws_session_id
    if hasattr(args, 'aws_session_token') and len(args.aws_session_token) != 0:
        parsed_params["AWS_SESSION_TOKEN"] = args.aws_session_token
    if hasattr(args, 'cassandra_keyspaces') and len(args.keyspaces) != 0:
        parsed_params["CASSANDRA_KEYSPACES"] = args.keyspaces

    return parsed_params


def download(args):
    log.info('Downloading DC/OS package with app id {} of version {} into target directory {}'.format(
        args.app_id, args.app_version, args.target_dir))
    backup.download_dcos_package(args.app_id, args.target_dir, args.app_version)
    if not args.only_conf:
        backup_params = parse_backup_restore_params(args)
        backup.download_task_data_on_s3(args.app_id, backup_params)


def install(args):
    log.info('Translating Mesos configurations to K8s configurations')
    is_ok = translate.translate_mesos_to_k8s(args.namespace, args.target_dir, args.config_file, args.target_file)
    if is_ok:
        translate.print_instructions(args.namespace, args.instance, args.target_file, args.operator_version)


def migrate(args):
    log.info("Restoring Schema and Data to K8s Cassandra")
    restore_params = parse_backup_restore_params(args)
    restore.restore_schema_and_data(args.namespace, args.instance, args.count, restore_params)


def main():
    log.basicConfig(level=log.INFO, format='[%(asctime)s] %(levelname)5s {%(filename)s:%(lineno)d} - %(message)s')

    class ShutdownHandler(log.Handler):
        def emit(self, record):
            log.shutdown()
            sys.exit(1)

    log.getLogger().addHandler(ShutdownHandler(level=50))

    # Dummy parent parser to share common global level args
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-t",
        "--target-dir",
        type=str,
        default="./cassandra_home",
        help='Folder to hold configuration of running DC/OS Cassandra service (defaults to ./cassandra_home)')

    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version', version='0.0.1-dev')
    subparsers = parser.add_subparsers(help='sub-commands available')

    # Step 1 : Backup the DC/OS Cassandra tasks data
    backup_cmd = subparsers.add_parser("backup",
                                       help='Backup the DC/OS package configurations and data',
                                       parents=[parent_parser])
    backup_cmd.add_argument("--app-id", type=str, default="cassandra", help="Service Name (defaults to cassandra)")
    backup_cmd.add_argument(
        "--only-conf",
        type=bool,
        default=False,
        help="Set True if only service configuration is required, no data backup (defaults to False)")
    backup_cmd.add_argument("--app-version",
                            type=str,
                            default="2.10.0-3.11.6",
                            help="Service Version (defaults to 2.10.0-3.11.6)")
    backup_cmd.add_argument("--snapshot-name",
                            type=str,
                            default="",
                            help="Snapshot or Backup Name (required, not applicable if --only-conf=True)")
    backup_cmd.add_argument("--bucket-name",
                            type=str,
                            default="",
                            help="S3 Bucket Name, without s3:// prefix (required, not applicable if --only-conf=True)")
    backup_cmd.add_argument("--keyspaces",
                            type=str,
                            default="",
                            help="Comma separated list of keyspace names for the Backup")
    backup_cmd.add_argument("--aws-key",
                            type=str,
                            default="",
                            help="AWS Access Key ID (required, not applicable if --only-conf=True)")
    backup_cmd.add_argument("--aws-secret",
                            type=str,
                            default="",
                            help="AWS Secret Access Key (required, not applicable if --only-conf=True)")
    backup_cmd.add_argument("--aws-session-id", type=str, default="", help="AWS Session ID")
    backup_cmd.add_argument("--aws-session-token", type=str, default="", help="AWS Session Token")
    backup_cmd.add_argument("--aws-region", type=str, default="us-west-2", help="AWS Region (defautls to us-west-2)")
    backup_cmd.add_argument("--https-proxy", type=str, default="", help="HTTPs Proxy")
    backup_cmd.set_defaults(func=download)

    # Step 2 : Migrate the configs from DC/OS Cassandra format to KUDO Cassandra format and print install instructions
    install_cmd = subparsers.add_parser(
        "install",
        help='Translate the DC/OS based configs to KUDO based configs and print install instructions.',
        parents=[parent_parser])
    install_cmd.add_argument(
        "-c",
        "--config-file",
        type=str,
        default="./cassandra_home/cassandra_env.json",
        help=
        "Path of the cassandra env file generated by backup command. (defaults to ./cassandra_home/cassandra_env.json)"
    )
    install_cmd.add_argument("-f",
                             "--target-file",
                             type=str,
                             default="./cassandra_home/params.yml",
                             help="Path of the target params file (defaults to ./cassandra_home/params.yml)")
    install_cmd.add_argument("--namespace",
                             type=str,
                             default="default",
                             help="Namespace of the cassandra pods (defaults to default)")
    install_cmd.add_argument("--instance",
                             type=str,
                             default="cassandra-instance",
                             help="Name of the Cassandra Kudo installation (defaults to cassandra-instance)")
    install_cmd.add_argument("--operator-version",
                             type=str,
                             default="0.1.2",
                             help="Kudo Cassandra version (defaults to 0.1.2)")
    install_cmd.set_defaults(func=install)

    # Step 3 : Migrate the schema and data from DC/OS Cassandra to KUDO Cassandra
    migrate_cmd = subparsers.add_parser(
        "migrate", help='Restore the Schema and Data from the backup of DC/OS Cassandra to KUDO Cassandra')
    migrate_cmd.add_argument("--namespace",
                             type=str,
                             default="default",
                             help="Namespace of the cassandra pods (defaults to default)")
    migrate_cmd.add_argument("--instance",
                             type=str,
                             default="cassandra-instance",
                             help="Name of the Cassandra Kudo installation (defaults to cassandra-instance)")
    migrate_cmd.add_argument("--count", type=int, default=3, help="Count of the cassandra node (defaults to 3)")
    migrate_cmd.add_argument("--snapshot-name", type=str, required=True, help="Snapshot or Backup Name")
    migrate_cmd.add_argument("--bucket-name", type=str, required=True, help="S3 Bucket Name, without s3:// prefix")
    migrate_cmd.add_argument("--aws-key", type=str, required=True, help="AWS Access Key ID")
    migrate_cmd.add_argument("--aws-secret", type=str, required=True, help="AWS Secret Access Key")
    migrate_cmd.add_argument("--aws-session-token", type=str, default="", help="AWS Session Token")
    migrate_cmd.add_argument("--aws-region", type=str, default="us-west-2", help="AWS Region (defautls to us-west-2)")
    migrate_cmd.set_defaults(func=migrate)

    args = parser.parse_args()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()
