from typing import List, Dict, Any, Optional
from dcos_migrate.system import DCOSClient, BackupList, ManifestList, Arg


class MigratePlugin(object):
    """docstring for Migrator."""
    plugin_name: str = 'OVERRIDE'
    backup_depends: List[str] = []
    backup_data_depends: List[str] = []
    migrate_depends: List[str] = []
    migrate_data_depends: List[str] = []

    def __init__(self, config: Dict[str, Any] = {}):
        self._config_options: List[Arg] = []
        self._config = config
        self._plugin_config: Optional[Dict[str, Any]] = {}
        if self.plugin_name in config:
            self._plugin_config = config[self.plugin_name]

    @property
    def config(self) -> Dict[str, Any]:
        """
        Get the full config. Including all plugins and global configurations
        """
        return self._config

    @config.setter
    def config(self, config: Dict[str, Any]) -> None:
        """
        Set config will also extract the config for this particular plugin
        stored in plugin_config
        """
        self._config = config
        self._plugin_config = None

        if self.plugin_name in config:
            self._plugin_config = config[self.plugin_name]

    @property
    def plugin_config(self) -> Optional[Dict[str, Any]]:
        """
        Get the config explicit for this plugin
        """
        return self._plugin_config

    @property
    def config_options(self) -> List[Arg]:
        return self._config_options

    def backup(self, client: DCOSClient, backupList: BackupList, **kwargs: Any) -> BackupList:
        """
        backup gets a DCOSClient and BackupList of all previously ran backups.
        It must return BackupList which gets merged with the current list of backups.

        Plugins should add data to containing Backups so users can reproduce their
        DC/OS clusters with apps, packages etc.
        """
        pass

    def backup_data(self, client: DCOSClient, backupList: BackupList, backupFolder: str, **kwargs: Any) -> None:
        """
        backup_data gets the DCOSCLient and a folder path. The data functions are
        less restrictive about the actual data in and outputs due to the huge difference
        from plugin to plugin.

        Plugins are expected to create at least a subfolder in backupFolder with their
        plugin_name
        """
        pass

    def migrate(self, backupList: BackupList, manifestList: ManifestList, **kwargs: Any) -> ManifestList:
        """
        migrate gets the complete list of backups BackupList and the list of all
        previously made Manifests in ManifestList.

        migrate must return a ManifestList with the Manifests of this plugin.
        """
        pass

    def migrate_data(self, backupList: BackupList, manifestList: ManifestList, backupFolder: str, migrateFolder: str,
                     **kwargs: Any) -> None:
        """
        migrate_data gets the backupList, ManifestList, backupFolder and a folder path.
        The data functions are less restrictive about the actual data in and outputs due to
        the huge difference from plugin to plugin.

        Plugins are expected to create at least a subfolder in migrateFolder with their
        plugin_name
        """
        pass
