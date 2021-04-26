import logging
import sys

from typing import Iterable, List, Optional, Callable

from dcos_migrate.system import DCOSClient, BackupList, ManifestList, ArgParse, Arg
from dcos_migrate.plugins.plugin_manager import PluginManager


class DCOSMigrate(object):
    """docstring for DCOSMigrate."""

    phases_choices = ["all", "backup", "backup_data", "migrate", "migrate_data"]

    config_defaults = [
        Arg(name="phase",
            nargs="?",
            choices=phases_choices,
            default="all",
            positional=True,
            help="phase to start with."),
        Arg(name="verbose",
            alternatives=["-v"],
            action="count",
            default=1,
            help="log verbosity. Default to critical and warnings")
    ]

    def __init__(self) -> None:
        super(DCOSMigrate, self).__init__()
        self.client = DCOSClient()
        self.pm = PluginManager()
        self.manifest_list = ManifestList()
        self.backup_list = BackupList()

        config = self.pm.config_options
        config.extend(self.config_defaults)
        self.argparse = ArgParse(
            config,
            prog='dcos-migrate',
            usage='Does a backup of your DC/OS cluster and migrates everything into K8s Manifests')

        self.phases: List[Callable[[Optional[str], bool], None]] = [
            self.initPhase, self.backup, self.backup_data, self.migrate, self.migrate_data
        ]

    @property
    def selected_phase(self) -> int:
        """returns the int(index) of the selected phase or 0"""
        return self.phases_choices.index(self.pm.config['global'].get('phase', "all"))

    def _end_process(self, message: str, exit_code: int = 0) -> int:
        print("Ending DC/OS migration - {}".format(message))
        return exit_code

    def run(self, args: Optional[List[str]] = None) -> int:
        """main entrypoint to start the migration script. Returns exit code as int"""
        self.handleArgparse(args)
        self.handleGlobal()

        for i, p in enumerate(self.phases):
            if self.selected_phase > i:
                p(None, True)
                continue
            p(None, False)

            if self.selected_phase and self.selected_phase == i:
                return self._end_process("selected phase {} reached".format(self.phases_choices[i]))

        return 0

    def handleGlobal(self) -> None:
        """handle global config before starting the process"""
        levels = [logging.CRITICAL, logging.WARNING, logging.INFO, logging.DEBUG]

        v = self.pm.config['global'].get('verbose', 1)
        level = levels[min(len(levels) - 1, v)]
        logging.basicConfig(level=level, force=True)

    def handleArgparse(self, args: Optional[List[str]] = None) -> None:
        if args is None:
            args = []
        self.pm.config = self.argparse.parse_args(args)

    def initPhase(self, pluginName: Optional[str] = None, skip: bool = False) -> None:
        """currently unused and empty method to cover all choice"""
        pass

    def backup(self, pluginName: Optional[str] = None, skip: bool = False) -> None:
        if skip:
            logging.info("skipping backup - trying to load from disk.")
            self.backup_list.load()
            return

        logging.info("Calling {} Backup Batches".format(len(self.pm.backup_batch)))
        for batch in self.pm.backup_batch:
            # each batch could also be executed in parallel.
            # But for now just start sequential
            for plugin in batch:
                logging.info("Calling backup for plugin {}".format(plugin.plugin_name))
                blist = plugin.backup(client=self.client, backupList=self.backup_list)
                if blist:
                    self.backup_list.extend(blist)

        self.backup_list.store()

    def backup_data(self, pluginName: Optional[str] = None, skip: bool = False) -> None:
        if skip:
            logging.info("skipping backup data")
            return
        # for batch in self.pm.backup_batch:
        #     # each batch could also be executed in parallel.
        #     # But for not just start sequencial
        #     for plugin in batch:
        #         blist = plugin.backup_data(DCOSClient=self.client)
        #         self.backup_data_list.extend(blist)

    def migrate(self, pluginName: Optional[str] = None, skip: bool = False) -> None:
        if skip:
            logging.info("skipping migrate - trying to load from disk.")
            self.manifest_list.load()
            return

        for batch in self.pm.migrate_batch:
            # each batch could also be executed in parallel.
            # But for not just start sequencial
            for plugin in batch:
                mlist = plugin.migrate(backupList=self.backup_list, manifestList=self.manifest_list)
                if mlist:
                    self.manifest_list.extend(mlist)

        self.manifest_list.store()

    def migrate_data(self, pluginName: Optional[str] = None, skip: bool = False) -> None:
        if skip:
            logging.info("skipping migrate data")
            return
        # for batch in self.pm.migrate_batch:
        #     # each batch could also be executed in parallel.
        #     # But for not just start sequencial
        #     for plugin in batch:
        #         mlist = plugin.migrate(
        #             backupList=self.backup_list, manifestList=self.manifest_list)
        #         self.manifest_list.extend(mlist)

    def get_plugin_names(self) -> Iterable[str]:
        return self.pm.plugins.keys()


def run() -> None:
    sys.exit(DCOSMigrate().run())
