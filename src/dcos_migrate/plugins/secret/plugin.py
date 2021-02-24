from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.plugins.cluster import ClusterPlugin
from dcos_migrate.system import DCOSClient, BackupList, Backup, Manifest, ManifestList
import dcos_migrate.utils as utils

from kubernetes.client.models import V1Secret, V1ObjectMeta  # type: ignore

import urllib
import base64
import logging
from base64 import b64encode
from typing import cast, Any, Dict, List


class DCOSSecretsService:

    def __init__(self, client: DCOSClient):
        self.client = client
        self.url = "{}/{}".format(self.client.dcos_url, 'secrets/v1')
        self.store = 'default'

    def list(self, path: str = '') -> List[str]:
        u = '{url}/secret/{store}/{path}?list=true'.format(
            url=self.url,
            store=urllib.parse.quote(self.store),
            path=urllib.parse.quote(path)
        )
        r = self.client.get(u)
        r.raise_for_status()
        return cast(List[str], r.json()['array'])

    def get(self, path: str, key: str) -> Dict[str, str]:
        # There are two types of secrets: text and binary.  Using `Accept: */*`
        # the returned `Content-Type` will be `application/octet-stream` for
        # binary secrets and `application/json` for text secrets.
        #
        # Returns the secret as:
        # {
        #   "path": "...",
        #   "key": "...",
        #   "type": "{text|binary}",
        #   "value": "base64(value)"
        # }
        full_path = (path + '/' + key).strip('/')
        url = self.url + '/secret/{store}/{path}'.format(
            store=urllib.parse.quote(self.store), path=urllib.parse.quote(full_path)
        )
        r = self.client.get(url, headers={'Accept': '*/*'})
        r.raise_for_status()
        content_type = r.headers['Content-Type']
        if content_type == 'application/octet-stream':
            response = {
                'type': 'binary',
                'value': base64.b64encode(r.content).decode('ascii')
            }
        else:
            assert content_type == 'application/json', content_type
            response = r.json()
            response['type'] = 'text'
            # Always encode the secret as base64, even when it is safe UTF-8 text.
            # This obscures the values to prevent unintentional exposure.
            response['value'] = base64.b64encode(
                response['value'].encode('utf-8')).decode('ascii')
        # Always add the `path` and `key` values to the JSON response. Ensure the key always has a
        # value by taking the last component of the path if necessary.
        if not key:
            parts = path.rsplit('/', 1)
            key = parts.pop()
            parts.append('')
            path = parts[0]
        response['path'] = path
        response['key'] = key
        return response


class SecretPlugin(MigratePlugin):
    """docstring for SecretPlugin."""

    plugin_name = "secret"
    depends_migrate = [ClusterPlugin.plugin_name]

    def __init__(self) -> None:
        super(SecretPlugin, self).__init__()

    def backup(self, client: DCOSClient, **kwargs) -> BackupList:  # type: ignore
        backupList = BackupList()
        sec = DCOSSecretsService(client)
        path = ""
        keys = sec.list(path)
        if keys:
            for key in keys:
                secData = sec.get(path, key)

                backupList.append(
                    Backup(self.plugin_name, Backup.renderBackupName(path + key), data=secData))

        return backupList

    def migrate(
        self, backupList: BackupList, manifestList: ManifestList, **kwargs: Any
    ) -> ManifestList:
        ml = ManifestList()

        for ba in backupList.backups(pluginName='secret'):
            assert isinstance(ba, Backup)
            metadata = V1ObjectMeta()
            metadata.annotations = {}

            clusterMeta = manifestList.clusterMeta()
            if clusterMeta:
                metadata.annotations = clusterMeta.annotations

            logging.debug("Found backup {}".format(ba))
            b = ba.data
            fullPath = "/".join(filter(None, [b["path"], b["key"]]))
            name = b["key"]

            metadata.annotations[utils.namespace_path("secret-path")] = fullPath
            metadata.name = utils.make_subdomain(name.split('/'))
            sec = V1Secret(metadata=metadata)
            sec.api_version = 'v1'
            sec.kind = 'Secret'
            # K8s requires secret values to be base64-encoded.  The secret value
            # is base64-encoded during backup so it can be passed as-is here.
            sec.data = {utils.dnsify(name): b['value']}

            manifest = Manifest(pluginName=self.plugin_name,
                                manifestName=utils.dnsify(fullPath))
            manifest.append(sec)

            ml.append(manifest)

        return ml
