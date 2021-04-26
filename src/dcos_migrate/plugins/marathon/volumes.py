import abc
from collections import defaultdict
from typing import Any, Dict, Iterator, List, Mapping, Sequence, Set

from .app_secrets import AppSecretMapping
from .common import InvalidAppDefinition, main_container, pod_spec_update, try_oneline_dump
from .mapping_utils import ListExtension, Translated
import dcos_migrate.utils as utils


def get_volumes(app: Dict[str, Any]) -> Sequence[Dict[str, Any]]:
    container: Dict[str, Any] = app.get('container', {})
    return container.get('volumes', [])


def is_resident(app: Dict[str, Any]) -> bool:
    return any('persistent' in v for v in get_volumes(app))


def volume_mount_name(volume_name: str) -> str:
    return utils.make_label(volume_name)


def translate_volume_claim_templates(app_name: str, volumes: Sequence[Dict[str, Any]]) -> Sequence[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []

    for v in volumes:
        if not 'persistent' in v:
            continue
        volume_name = volume_mount_name(v['containerPath'])
        size = int(v['persistent']['size'])

        output.append({
            'metadata': {
                'name': volume_name
            },
            'spec': {
                'accessModes': ['ReadWriteOnce'],
                'resources': {
                    'requests': {
                        'storage': str(size) + 'Mi'
                    }
                }
            }
        })

    return output


def translate_volumes(volumes: Iterator[Dict[str, Any]], app_secrets: AppSecretMapping) -> Translated:
    mappers = [_HostPathVolumeMapper(), _SecretVolumeMapper(app_secrets), _PersistentVolumeMapper(volumes)]

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


def _is_sandbox_relative_path(path: str) -> bool:
    return not path.startswith('/')


class _PersistentVolumeMapper(_VolumeMapper):
    def __init__(self, all_volumes: Iterator[Dict[str, Any]]) -> None:
        super().__init__()
        self._result = Translated()
        self._index = 0
        self.all_volumes = all_volumes
        self.persistent_volume_names = [v['containerPath'] for v in self.all_volumes if v.get('persistent', None)]

    def consume(self, volume: Dict[str, Any]) -> bool:
        fields = volume.copy()

        if 'persistent' in fields:
            persistent_volume_name = volume['containerPath']
            mapped_volume = [v for v in self.all_volumes if v.get('hostPath') == persistent_volume_name]
            if len(mapped_volume) == 0:
                # This persistent volume has no mapping, we cannot expose it
                return False
            else:
                # This persistent volume has a mapping! But we don't actually do anything with it here. A persistentVolumeClaim is generated from it elsewhere.
                return True

        elif ('hostPath' in volume) and (_is_sandbox_relative_path(volume['hostPath'])):
            fields = volume.copy()

            try:
                name = fields.pop('hostPath')
                container_path = fields.pop('containerPath')
                mode = fields.pop('mode')
            except KeyError:
                return False

            if fields:
                return False

            if name in self.persistent_volume_names:
                # There's a persistent volume to which we can map this!
                mount = Translated(
                    main_container({
                        "volumeMounts":
                        ListExtension([{
                            "name": name,
                            "mountPath": container_path,
                            "readOnly": mode == "RO",
                        }])
                    }))
                self._result = self._result.merged_with(mount)
                return True
            else:
                return False
        else:
            # no persistent mapping
            return False

    def result(self) -> Translated:
        return self._result


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
