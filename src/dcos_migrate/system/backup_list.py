from typing import Optional
from .storable_list import StorableList
from .backup import Backup
from jsonpath_ng import parse  # type: ignore


class BackupList(StorableList):
    """docstring for BackupList."""

    def __init__(self, dry: bool = False, path: str = './dcos-migrate/backup'):
        super(BackupList, self).__init__(path)
        self._dry = dry

    def backups(self, pluginName: str) -> 'BackupList':
        newList = BackupList()

        for b in self:
            if b.plugin_name == pluginName:
                newList.append(b)
        return newList

    def backup(self, pluginName: str, backupName: str) -> Optional[Backup]:
        for b in self.backups(pluginName=pluginName):
            assert isinstance(b, Backup)
            if b.name == backupName:
                return b
        return None

    def match_jsonpath(self, jsonPath: str) -> 'BackupList':
        bl = BackupList()
        jsonpath_expr = parse(jsonPath)

        for b in self:
            # this is quite stupid but related to the Backup object structure
            # maybe there is a better way to make .data directly part of the list
            assert isinstance(b, Backup)
            res = jsonpath_expr.find([b.data])
            if res and len(res) > 0:
                bl.append(b)

        return bl

    def append_data(self, pluginName: str, backupName: str,  # type: ignore
                    extension: str, data: str, **kwargs) -> None:
        b = Backup(pluginName=pluginName, backupName=backupName,
                   extension=extension)
        b.deserialize(data)

        self.append(b)
