from dcos_migrate.system import Manifest, ManifestList, Migrator, with_comment
import dcos_migrate.utils as utils
from kubernetes.client.models import V1Deployment, V1Service, V1ObjectMeta, V1Secret  # type: ignore
from kubernetes.client import ApiClient, V1StatefulSet  # type: ignore

from .app_translator import ContainerDefaults, translate_app, Settings
from .app_secrets import TrackingAppSecretMapping, SecretRemapping
from .service_translator import translate_service
from .stateful_copy import make_sleeper_stateful_set, configure_stateful_migrate

import logging
import sys
from typing import Any, DefaultDict, Mapping, Optional, Set
from collections import defaultdict


class NodeLabelTracker(object):
    def __init__(self) -> None:
        self.labels_by_app: Mapping[str, Set[str]] = defaultdict(set)

    def add_app_node_labels(self, marathon_app_id: str, labels: Set[str]) -> None:
        self.labels_by_app[marathon_app_id].update(labels)

    def get_apps_by_label(self) -> Mapping[str, Set[str]]:
        apps_by_label: DefaultDict[str, Set[str]] = defaultdict(set)
        for app, labels in self.labels_by_app.items():
            for label in labels:
                apps_by_label[label].add(app)

        return dict(apps_by_label)


@with_comment
class V1ServiceWithComment(V1Service):  # type: ignore
    pass


@with_comment
class V1DeploymentWithComment(V1Deployment):  # type: ignore
    pass


@with_comment
class V1StatefulSetWithComment(V1StatefulSet):  # type: ignore
    pass


class MarathonMigrator(Migrator):
    """docstring for MarathonMigrator."""
    def __init__(self, node_label_tracker: Optional[NodeLabelTracker] = None, **kw: Any):
        super(MarathonMigrator, self).__init__(**kw)

        self._node_label_tracker = NodeLabelTracker() if node_label_tracker is None\
            else node_label_tracker

        assert self.object is not None
        self._secret_mapping = TrackingAppSecretMapping(self.object['id'], self.object.get('secrets', {}))

        self.translate = {
            "id": self.translate_marathon,
        }

    def translate_marathon(self, key: str, value: str, full_path: str) -> None:
        if self.object is None:
            raise Exception("self.object is not set; this is a bug")

        labels = self.object.get('labels', {})
        dcos_package_framework_name = labels.get("DCOS_PACKAGE_FRAMEWORK_NAME")
        if dcos_package_framework_name:
            logging.warning('Not translating app %s: it runs Mesos framework %s', value, dcos_package_framework_name)
            return

        settings = Settings(
            container_defaults=ContainerDefaults("alpine:latest", "/"),
            app_secret_mapping=self._secret_mapping,
        )

        self.manifest = Manifest(pluginName="marathon", manifestName=self.dnsify(value))

        assert self.object is not None

        translated = translate_app(self.object, settings)

        kc = ApiClient()
        if translated.deployment['kind'] == "StatefulSet":
            sleeper_stateful_set = make_sleeper_stateful_set(translated.deployment)
            dapp = kc._ApiClient__deserialize(sleeper_stateful_set, V1StatefulSetWithComment)
            try:
                configure_stateful_migrate(original_marathon_app=self.object,
                                           k8s_translate_result=translated.deployment)
            except:
                print("Unexpected error while preparing Marathon stateful migration:", sys.exc_info()[0])
                raise
        else:
            dapp = kc._ApiClient__deserialize(translated.deployment, V1DeploymentWithComment)

        dapp.set_comment(translated.warnings)

        self.manifest.append(dapp)
        self._node_label_tracker.add_app_node_labels(self.object['id'], translated.required_node_labels)

        service, service_warnings = translate_service(dapp.metadata.labels['app'], self.object)
        if service:
            kc2 = ApiClient()
            dservice = kc2._ApiClient__deserialize(service, V1ServiceWithComment)
            dservice.set_comment(service_warnings)
            self.manifest.append(dservice)

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
