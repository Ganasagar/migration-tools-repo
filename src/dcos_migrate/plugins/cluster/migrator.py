from dcos_migrate.system import Migrator
from typing import Any


class ClusterMigrator(Migrator):
    """docstring for ClusterMigrator."""
    def __init__(self, **kw: Any):
        super(ClusterMigrator, self).__init__(**kw)
        self.translate = {}
