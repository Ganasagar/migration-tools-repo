from dcos_migrate.system import Migrator
from typing import Any


class JenkinsMigrator(Migrator):
    """docstring for JenkinsMigrator."""

    def __init__(self, **kw: Any):
        super(JenkinsMigrator, self).__init__(**kw)
        self.translate = {}
