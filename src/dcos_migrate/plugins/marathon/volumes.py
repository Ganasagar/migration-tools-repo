import abc
from collections import defaultdict
from typing import Any, Dict, Iterator, List, Mapping

from .app_secrets import AppSecretMapping
from .common import InvalidAppDefinition, main_container, pod_spec_update, try_oneline_dump
from .mapping_utils import ListExtension, Translated
import dcos_migrate.utils as utils


def translate_volumes(volumes: Iterator[Dict[str, Any]], app_secrets: AppSecretMapping) -> Translated:
    mappers = [_HostPathVolumeMapper(), _SecretVolumeMapper(app_secrets)]

    result = Translated()
    for volume in volumes:
        consuming_mapper_names = [m.__class__.__name__ for m in mappers if m.consume(volume)]
        if len(consuming_mapper_names) > 1:
            raise Exception("A volume {} can be translated by several mappers: {}."
                            " This is likely a bug.".format(try_oneline_dump(volume), consuming_mapper_names))

        if not consuming_mapper_names:
            result = result.merged_with(
                Translated(warnings=["Cannot translate a volume: {}".format(try_oneline_dump(volume))]))

    for mapper in mappers:
        result = result.merged_with(mapper.result())

    return result


class _VolumeMapper(object):
    @abc.abstractmethod
    def result(self) -> Translated:
        """Returns the translation result."""
        pass

    @abc.abstractmethod
    def consume(self, volume: Dict[str, Any]) -> bool:
        """
        Called for each volume in the app.

        Returns `True` if the volume has been mapped by this mapper and `False` otherwise,
        so that a warning can be emitted if no mapper could translate a volume.
        """
        pass


class _HostPathVolumeMapper(_VolumeMapper):
    def __init__(self) -> None:
        super().__init__()
        self._result = Translated()
        self._index = 0

    def consume(self, volume: Dict[str, Any]) -> bool:
        fields = volume.copy()
        try:
            container_path = fields.pop('containerPath')
            host_path = fields.pop('hostPath')
            mode = fields.pop('mode')
        except KeyError:
            return False

        if fields:
            return False

        if not host_path.startswith('/'):
            return False

        if mode not in ("RO", "RW"):
            raise InvalidAppDefinition("Invalid volume mode {}".format(mode))

        name = 'volume-{}'.format(self._index)
        self._index += 1

        mount = Translated(
            main_container({
                "volumeMounts":
                ListExtension([{
                    "name": name,
                    "mountPath": container_path,
                    "readOnly": mode == "RO",
                }])
            }))

        pod_volume = Translated(
            pod_spec_update({"volumes": ListExtension([{
                "name": name,
                "hostPath": {
                    "path": host_path
                }
            }])}))

        self._result = self._result.merged_with(mount.merged_with(pod_volume))
        return True

    def result(self) -> Translated:
        return self._result


class _SecretVolumeMapper(_VolumeMapper):
    def __init__(self, app_secret_mapping: AppSecretMapping):
        super().__init__()
        self._app_secret_mapping = app_secret_mapping
        self._mounts = Translated()

        # We do not expect that AppSecretMapping returns the same K8s secret
        # name for all the secrets in the app. Hence, to generate secret volumes,
        # we store a list of used keys for each k8s secret.
        self._used_secret_keys: Mapping[str, List[str]] = defaultdict(list)

    @staticmethod
    def secret_volume_name(k8s_secret_name: str) -> str:
        return utils.make_label('secrets-' + k8s_secret_name)

    def consume(self, volume: Dict[str, Any]) -> bool:
        fields = volume.copy()
        try:
            container_path = fields.pop("containerPath")
            app_secret_name = fields.pop("secret")
        except KeyError:
            return False

        if fields:
            return False

        ref = self._app_secret_mapping.get_reference(app_secret_name)

        self._used_secret_keys[ref.secret_name].append(ref.key)

        self._mounts = self._mounts.merged_with(
            Translated(
                main_container({
                    "volumeMounts":
                    ListExtension([{
                        "name": self.secret_volume_name(ref.secret_name),
                        "subPath": ref.key,
                        "mountPath": container_path,
                        "readOnly": True,
                    }])
                })))

        return True

    def result(self) -> Translated:
        update = self._mounts
        for secret_name, keys in self._used_secret_keys.items():
            volume = Translated(
                pod_spec_update({
                    "volumes":
                    ListExtension([{
                        "name": self.secret_volume_name(secret_name),
                        "secret": {
                            "secretName": secret_name,
                            # TODO: Enforce dumping the "mode" value as an octal.
                            "items": [{
                                "key": k,
                                "path": k,
                                "mode": 0o777
                            } for k in keys],
                        }
                    }])
                }))

            update = update.merged_with(volume)

        return update
