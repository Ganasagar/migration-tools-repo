from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.plugins.marathon import MarathonPlugin
from dcos_migrate.system import DCOSClient, BackupList, Backup
from base64 import b64decode
import json
from typing import Any

# we could have an abstract for cosmos services as we can extract package options in the same way


class JenkinsPlugin(MigratePlugin):
    """docstring for JenkinsPlugin."""
    plugin_name = "jenkins"

    backup_depends = [MarathonPlugin.plugin_name]

    def __init__(self) -> None:
        super(JenkinsPlugin, self).__init__()

    def backup(self, client: DCOSClient, backupList: BackupList, **kwargs: Any) -> BackupList:
        bl = BackupList()
        for b in backupList.backups(pluginName="marathon"):
            assert isinstance(b, Backup)
            if (
                b.data
                and 'labels' in b.data
                and "DCOS_PACKAGE_NAME" in b.data['labels']
                and b.data['labels']['DCOS_PACKAGE_NAME'] == "jenkins"
            ):
                # we found a jenkins package lets extract the config
                if 'DCOS_PACKAGE_OPTIONS' in b.data['labels']:
                    options_str = b64decode(
                        b.data['labels']['DCOS_PACKAGE_OPTIONS'])

                    options = json.loads(options_str)
                    data = {
                        "packageName": b.data['labels']['DCOS_PACKAGE_NAME'],
                        "version": b.data['labels']['DCOS_PACKAGE_VERSION'],
                        "options": options
                    }

                    bl.append(
                        Backup(pluginName=self.plugin_name, backupName=Backup.renderBackupName(
                            b.data['labels']['DCOS_SERVICE_NAME']), data=data
                        )
                    )
        return bl
