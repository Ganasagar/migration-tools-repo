from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.system import BackupList, DCOSClient, Backup, Manifest, ManifestList
import dcos_migrate.utils as utils
from kubernetes.client.models import V1ConfigMap, V1ObjectMeta  # type: ignore
import json
import logging
import datetime
from base64 import b64encode
from typing import Any


class ClusterPlugin(MigratePlugin):
    """docstring for ClusterPlugin."""
    plugin_name = "cluster"

    # No depends wanna run first

    def __init__(self) -> None:
        super(ClusterPlugin, self).__init__()

    def backup(self, client: DCOSClient, backupList: BackupList, **kwargs: Any) -> BackupList:
        bl = BackupList()
        metadataResp = client.get(client.full_dcos_url('/metadata'))
        stateSumResp = client.get(client.full_dcos_url('/mesos/master/state-summary'))

        metadata = metadataResp.json()
        state = stateSumResp.json()

        data = {
            "CLUSTER_ID": metadata['CLUSTER_ID'],
            "CLUSTER": state['cluster'],
            "MESOS_MASTER_STATE-SUMMARY": state,
            "BACKUP_DATE": str(datetime.date.today())
        }

        bl.append(Backup(pluginName=self.plugin_name, backupName="default", data=data))

        return bl

    def migrate(self, backupList: BackupList, manifestList: ManifestList, **kwargs: Any) -> ManifestList:
        ml = ManifestList()

        clusterBackup = backupList.backup(pluginName=self.plugin_name, backupName='default')

        if not clusterBackup:
            logging.critical("Cluster backup not found. Cannot provide DC/OS annotations")
            return ml
        metadata = V1ObjectMeta(name="dcos-{}".format(clusterBackup.data['CLUSTER_ID']))
        metadata.annotations = {
            utils.namespace_path("cluster-id"): clusterBackup.data['CLUSTER_ID'],
            utils.namespace_path("cluster-name"): clusterBackup.data['CLUSTER'],
            utils.namespace_path("backup-date"): clusterBackup.data['BACKUP_DATE'],
        }
        cfgmap = V1ConfigMap(metadata=metadata)
        # models do not set defaults -.-
        cfgmap.kind = "ConfigMap"
        cfgmap.api_version = "v1"
        cfgmap.data = {
            'MESOS_MASTER_STATE_SUMMARY_BASE64':
            b64encode(json.dumps(clusterBackup.data['MESOS_MASTER_STATE-SUMMARY']).encode('ascii'))
        }

        manifest = Manifest(pluginName=self.plugin_name, manifestName="dcos-cluster")
        manifest.append(cfgmap)

        ml.append(manifest)

        return ml
