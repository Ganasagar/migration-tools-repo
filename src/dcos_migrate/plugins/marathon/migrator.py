from dcos_migrate.system import Manifest, ManifestList, Migrator, with_comment
import dcos_migrate.utils as utils
from kubernetes.client.models import V1Deployment, V1ObjectMeta, V1Secret  # type: ignore
from kubernetes.client import ApiClient  # type: ignore

from .app_translator import ContainerDefaults, translate_app, Settings
from .app_secrets import TrackingAppSecretMapping, SecretRemapping

from typing import Any, Optional


@with_comment
class V1DeploymentWithComment(V1Deployment):  # type: ignore
    pass


class MarathonMigrator(Migrator):
    """docstring for MarathonMigrator."""

    def __init__(self, **kw: Any):
        super(MarathonMigrator, self).__init__(**kw)
        assert self.object is not None
        self._secret_mapping = TrackingAppSecretMapping(
            self.object['id'], self.object.get('secrets', {}))

        self.translate = {
            "id": self.translate_marathon,
        }

    def translate_marathon(self, key: str, value: str, full_path: str) -> None:
        settings = Settings(
            container_defaults=ContainerDefaults("alpine:latest", "/"),
            app_secret_mapping=self._secret_mapping,
        )

        self.manifest = Manifest(
            pluginName="marathon", manifestName=self.dnsify(value))
        assert self.object is not None
        app, warnings = translate_app(self.object, settings)

        kc = ApiClient()
        dapp = kc._ApiClient__deserialize(app, V1DeploymentWithComment)
        dapp.set_comment(warnings)

        self.manifest.append(dapp)

        for remapping in self._secret_mapping.get_secrets_to_remap():
            secret = _create_remapped_secret(self.manifest_list, remapping, self.object['id'])
            if secret is not None:
                self.manifest.append(secret)


class NoMigratedSecretFound(RuntimeError):
    pass


def _create_remapped_secret(
    manifest_list: Optional[ManifestList],
    remapping: SecretRemapping,
    app_id: str,
) -> Optional[V1Secret]:

    if not remapping.key_mapping:
        return None

    assert manifest_list is not None
    clusterMeta: Optional[V1ObjectMeta] = manifest_list.clusterMeta()

    metadata = V1ObjectMeta(annotations={})
    if clusterMeta is not None:
        metadata.annotations = clusterMeta.annotations

    metadata.annotations[utils.namespace_path("marathon-appid")] = app_id
    metadata.name = utils.dnsify(remapping.dest_name)
    secret = V1Secret(metadata=metadata, data={})
    secret.api_version = 'v1'
    secret.kind = 'Secret'
    if remapping.dest_type is not None:
        secret.type = remapping.dest_type

    for source_key, destination_key in remapping.key_mapping.items():
        sourceSecret = manifest_list.manifest(pluginName='secret', manifestName=source_key)
        if not sourceSecret:
            raise NoMigratedSecretFound('No migrated secret "{}" found'.format(source_key))

        [value] = sourceSecret[0].data.values()
        secret.data[destination_key] = value

    return secret
