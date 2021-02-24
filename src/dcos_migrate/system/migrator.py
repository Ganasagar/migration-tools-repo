import logging
from jsonpath_ng.ext import parse  # type: ignore
from typing import Any, Callable, Dict, Optional
import dcos_migrate.utils as utils
from .backup import Backup
from .backup_list import BackupList
from .manifest import Manifest
from .manifest_list import ManifestList


class Migrator(object):
    """docstring for Migrator."""

    def __init__(
        self,
        backup: Optional[Backup] = None,
        backup_list: Optional[BackupList] = None,
        manifest_list: Optional[ManifestList] = None,
        object: Optional[Dict[str, Any]] = None
    ):
        super(Migrator, self).__init__()
        self.backup = backup
        self.object = object
        if backup is not None:
            self.object = backup.data
        self.backup_list = backup_list
        self.manifest_list = manifest_list
        self.manifest: Optional[Manifest] = None

        self.translate: Dict[str, Callable[[str, Any, str], None]] = {}

    def valid(self) -> bool:
        """Returns True if self.object is what we expect"""
        return True

    def dnsify(self, name: str) -> str:
        new_name = utils.dnsify(name)
        if not name == new_name:
            logging.info(
                f'"{name}" is not a valid name in kubernetes. converted it to "{new_name}".'
            )
        return new_name

    def migrate(self) -> Optional[Manifest]:
        if not self.valid():
            return None

        for k, v in self.translate.items():
            expr = parse(k)
            for match in expr.find(self.object):
                v(str(match.path), match.value, str(match.full_path))

        return self.manifest

    def noEquivalent(self, key: str, value: str, full_path: str) -> None:
        logging.warning("No equivalent available for {full_path} with value {value}".format(
            full_path=full_path, value=value))
