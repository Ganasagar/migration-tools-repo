import logging
from typing import Any

from dcos_migrate.plugins import plugin
from dcos_migrate import system

from dcos.errors import DCOSHTTPException  # type: ignore

from . import edgelb
from . import migrator


class EdgeLBPlugin(plugin.MigratePlugin):
    plugin_name = "edgelb"

    def backup(self, client: system.DCOSClient, backupList: system.BackupList, **kwargs: Any) -> system.BackupList:
        service_path = "/service/edgelb"
        bl = system.BackupList()

        if "service_name" in kwargs:
            service_path = "/service/{}/api".format(kwargs["service_name"])

        url = "{}{}/v2/pools".format(client.dcos_url, service_path)

        try:
            resp = client.get(url)
        except DCOSHTTPException as e:
            if e.status() == 404:
                logging.warning("EdgeLB not installed. Skipping")
            else:
                logging.critical("Unexpected HTTP error for EdgeLB {}".format(e))
            return bl

        pools = resp.json()

        if "pool_name" in kwargs:
            pools = [p for p in pools if p["name"] == kwargs["pool_name"]]

        for pool in pools:
            parsed_pool = edgelb.parse_pool(pool)

            if parsed_pool:
                backup = system.Backup(
                    self.plugin_name,
                    system.Backup.renderBackupName(pool["name"]),
                    parsed_pool,
                )
                bl.append(backup)

        return bl

    def migrate(self, backupList: system.BackupList, manifestList: system.ManifestList,
                **kwargs: Any) -> system.ManifestList:
        ml = system.ManifestList()

        for b in backupList.backups(pluginName=self.plugin_name):
            mig = migrator.Ingress(
                backup=b,
                backup_list=backupList,
                manifest_list=manifestList,
            )

            manifest = mig.migrate()
            if manifest:
                ml.append(manifest)

        return ml
