#!/usr/bin/env bash

show_help() {
cat << EOF
Usage: dcos_cassandra_restore.sh [-h] [-i INSTANCE] [-x POD_INDEX] [-n NAMESPACE]
                                 -b BUCKET_NAME -p SNAPSHOT_NAME [-r AWS_REGION]
                                 -k AWS_KEY -s AWS_SECRET [-t AWS_TOKEN]
Options:
        -h, --help                      display this help and exit
        -i, --instance INSTANCE         cassandra instance name on K8s (defaults to cassandra-instance)
        -x, --pod-index POD_INDEX       pod index (defaults to 0)
        -n, --namespace NAMESPACE       namespace on K8s (defaults to default)
        -b, --bucket-name BUCKET_NAME   name of the S3 Bucket
        -p, --sanpshot SNAPSHOT_NAME    snapshot name or backup name
        -r, --aws-region AWS_REGION     aws region (defaults to us-west-2)
        -k, --aws-key AWS_KEY           aws access key id
        -s, --aws-secret AWS_SECRET     aws secret access key
        -t, --aws-token AWS_TOKEN       aws session token
EOF
}

# Initialize
instance_name="cassandra-instance"
pod_index=0
namespace="default"
bucket_name=
snapshot_name=
aws_region="us-west-2"
aws_key=
aws_secret=
aws_token=

# Parse the arguments
while [[ $# -gt 0 ]]; do
  opt="$1"
  case $opt in
    -i|--instance)
      instance_name="$2"
      shift
      shift
      ;;
    -x|--pod-index)
      pod_index="$2"
      shift
      shift
      ;;
    -n|--namespace) 
      namespace="$2"
      shift
      shift
      ;;
    -b|--bucket-name)
      bucket_name="$2"
      shift
      shift
      ;;
    -p|--snapshot)
      snapshot_name="$2"
      shift
      shift
      ;;
    -r|--aws-region)
      aws_region="$2"
      shift
      shift
      ;;
    -k|--aws-key)
      aws_key="$2"
      shift
      shift
      ;;
    -s|--aws-secret)
      aws_secret="$2"
      shift
      shift
      ;;
    -t|--aws-token)
      aws_token="$2"
      shift
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      show_help
      exit 1
      ;;
  esac
done

# Check for required option
if [[ -z $bucket_name || -z $snapshot_name || -z $aws_key || -z $aws_secret ]]; then
  echo ">> One of required option is missing; --bucket-name, --snapshot, --aws-key and --aws-secret are required!"
  exit 1
fi

# Export environment variables
export AWS_REGION=$aws_region
export AWS_ACCESS_KEY_ID=$aws_key
export AWS_SECRET_ACCESS_KEY=$aws_secret
export AWS_SESSION_TOKEN=$aws_token

pod_dns="${instance_name}-node-${pod_index}.${instance_name}-svc.${namespace}.svc.cluster.local"

# Download backup locally
echo ">> Downloading backup '${snapshot_name}' from bucket '${bucket_name}' for 'node-${pod_index}'..."
mkdir -p /tmp/cassandra_backup
aws s3 cp s3://${bucket_name}/${snapshot_name}/node-${pod_index} /tmp/cassandra_backup/ --recursive
result=$?
if [[ $result == 0 ]]; then
  echo ">> Backup Downloaded."
else
  echo ">> Backup download failed with exit code $result"
  exit $result
fi

# Restore Schema
if [[ -f '/tmp/cassandra_backup/schema.cql' ]]; then
  echo ">> Restoring Schema to '${pod_dns}'..."
  cqlsh -e "source '/tmp/cassandra_backup/schema.cql'" ${pod_dns}
else
  echo ">> Invalid Backup, schema file not found."
  exit 1
fi

# Restore Data
echo ">> Restoring Data to '${pod_dns}'..."
for f in $(find /tmp/cassandra_backup -maxdepth 1 -mindepth 1 -type d ! -name "system_*" ! -name "system") ; do
  for t in $(find "$f" -maxdepth 1 -mindepth 1 -type d) ; do
    echo ">> Loading table ${t}"
    sstableloader -f /etc/cassandra/cassandra.yaml -d ${pod_dns} "${t}"
    result=$?
    if [ $result != 0 ]; then
      echo ">> Table loader failed with exit code $result"
      exit $result
    fi
  done
done

rm -rf /tmp/cassandra_backup
echo ">> Successfully Restored Schema and Data."

