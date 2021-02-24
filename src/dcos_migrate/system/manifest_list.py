from typing import cast, Optional
from .storable_list import StorableList
from .manifest import Manifest
from kubernetes.client.models import V1ObjectMeta  # type: ignore
import copy


class ManifestList(StorableList):
    """docstring for ManifestList."""

    def __init__(self, dry: bool = False, path: str = './dcos-migrate/migrate'):
        super(ManifestList, self).__init__(path)
        self._dry = dry

    def manifest(self, pluginName: str, manifestName: str) -> Optional[Manifest]:
        ml = self.manifests(pluginName=pluginName)
        for m in ml:
            assert isinstance(m, Manifest)
            if m.name == manifestName:
                return m

        return None

    def clusterMeta(self) -> Optional[V1ObjectMeta]:
        clustermanifests = self.manifests('cluster')
        # cluster creates a single manifest with a single Configmap
        if clustermanifests and clustermanifests[0] and cast(Manifest, clustermanifests[0])[0]:
            clustercfg = cast(Manifest, clustermanifests[0])[0]
            return copy.deepcopy(clustercfg.metadata)

        return None

    def manifests(self, pluginName: str) -> 'ManifestList':
        ml = ManifestList()
        for m in self:
            if m and m.plugin_name == pluginName:
                ml.append(m)

        return ml

    def append_data(self, pluginName: str, backupName: str,  # type: ignore
                    extension: str, data: str, **kw) -> None:
        b = Manifest(pluginName=pluginName, manifestName=backupName,
                     extension=extension)
        b.deserialize(data)

        self.append(b)
