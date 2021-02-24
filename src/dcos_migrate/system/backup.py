import json
from typing import Any, Dict


class Backup(object):
    """docstring for Backup."""

    def __init__(
        self, pluginName: str, backupName: str, data: Dict[str, Any] = {}, extension: str = 'json'
    ):
        super(Backup, self).__init__()
        self._plugin_name = pluginName
        if "/" in backupName:
            raise AttributeError(
                "backupName {} contains not allowed '/'".format(backupName))
        self._name = backupName
        self._data = data
        self._extension = extension
        self._serializer = json.dumps
        self._deserializer = json.loads

    @staticmethod
    def renderBackupName(name: str) -> str:
        # replace path with dashes
        return "-".join(list(filter(None, name.split("/"))))

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def extension(self) -> str:
        return self._extension

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def serialize(self) -> str:
        return self._serializer(self._data)

    def deserialize(self, data: str) -> None:
        self._data = self._deserializer(data)
