import abc
from typing import Dict, Mapping, NamedTuple, Optional, Sequence

import dcos_migrate.utils as utils

from .common import InvalidAppDefinition


class SecretReference(NamedTuple):
    secret_name: str
    key: str


class AppSecretMapping(abc.ABC):
    """
    Provides a mapping from Marathon app's internal secret names
    to name(s) and keys in the migrated DCOS secret.
    """
    @abc.abstractmethod
    def get_reference(self, app_secret_name: str) -> SecretReference:
        pass

    @abc.abstractmethod
    def get_image_pull_secret_name(self, app_secret_name: str) -> str:
        """
        A docker pull config secret of an app has to be converted into
        a dedicated secret with a single `.dockerconfigjson` key;
        hence, it should be mapped separately.
        """
        pass


class SecretRemapping(NamedTuple):
    """Settings for remapping keys of the monolithic DCOS secret into app-specific secrets"""
    dest_name: str
    dest_type: Optional[str]
    key_mapping: Dict[str, str]


class TrackingAppSecretMapping(AppSecretMapping):
    """
    Tracks which secrets are used by callers of `AppSecretMapping` interface
    and reports them via `get_secrets_to_remap()`.
    """

    def __init__(
        self,
        app_id: str,
        app_secrets: Mapping[str, Mapping[str, str]],
    ):
        self._app_secrets = app_secrets

        self._generic_remapping = SecretRemapping(
            dest_name="marathonsecret-{}".format(utils.dnsify(app_id)),
            dest_type=None,
            key_mapping={}
        )

        self._image_pull_remapping = SecretRemapping(
            dest_name="marathonpullcfgsecret-{}".format(utils.dnsify(app_id)),
            dest_type="kubernetes.io/dockerconfigjson",
            key_mapping={}
        )

    def __get_k8s_secret_key(self, app_secret_name: str) -> str:
        try:
            dcos_name = self._app_secrets[app_secret_name]['source']
        except KeyError:
            raise InvalidAppDefinition(
                'No source specified for a secret "{}"'.format(app_secret_name))

        return utils.dnsify(dcos_name)

    def get_reference(self, app_secret_name: str) -> SecretReference:
        k8s_key = self.__get_k8s_secret_key(app_secret_name)
        self._generic_remapping.key_mapping[k8s_key] = k8s_key
        return SecretReference(self._generic_remapping.dest_name, k8s_key)

    def get_image_pull_secret_name(self, app_secret_name: str) -> str:
        k8s_key = self.__get_k8s_secret_key(app_secret_name)

        existing = next(iter(self._image_pull_remapping.key_mapping), None)
        if existing not in (None, k8s_key):
            raise Exception(
                "`get_image_pull_secret_reference()` called for two different secrets ({} and {})."
                " This is a bug.".format(existing, k8s_key))

        self._image_pull_remapping.key_mapping[k8s_key] = ".dockerconfigjson"
        return self._image_pull_remapping.dest_name

    def get_secrets_to_remap(self) -> Sequence[SecretRemapping]:
        return (self._generic_remapping, self._image_pull_remapping)
