import base64
import json
import random
import stat
import string
import subprocess
from pathlib import Path

import pytest
import requests

from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_ee
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output
from dcos_test_utils.dcos_cli import DcosCli
from passlib.hash import sha512_crypt

from secrets import backup, migrate

# Prefix for metadata label and annotation keys
DCOS_PREFIX = 'dcos-migration.d2iq.com'

PRIVATE_KEY = """
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7zYQ8wdXCQQrj
jxNGIXAMQWYXW7krsT0gkH2jOv1M5kCIbFF9eJoJtj7zSzGBlsIVFzjls73ageqP
zACRxU7P4D/IfEomgyg6E1TayHfVwwGG+4wUBxvvFgaK2WlCpLThLjgoOnMrl3id
TZ4uVqxlhSSzG1+sygx6nZgBtQ2aS0Bdg6RZ2slI+00TR1Hngi/PKBVDkCRWFGH+
OJFUkGNLf4IQEQ4R1V143R5QIVG2eyxKEDbxM1xFimocLaOGomdRV4/FmQgn031T
olrITFwA7vywC/VflvC1Olvcf5iP93krQdqopZ9Ut8EFsFLWF8iiGCc6Dpdj35MJ
c8og4S1VAgMBAAECggEAOxPDbXlsTNc5Hax8W6tZHAHWo7Ju5ZezqvLJEvgThoVH
96JbYCT4D+YMl2wn/qP2GbxcYaXRK1OC/gkmhLSUvj/E0MSIbuUDWoGKR+iYCd52
NIgc4I/78ZH0LOmHezdkzxFDCSSZ5jSX9KPeBqWtRaJEkTMjPa+xjUDV+HOD++z1
BS5bSJY9DLkh2gH2IHk4ypla8z7QP+N1KiKrjyLWuHdyUWvcXZ77ae2rGL8Th6mD
64R189xfUhcXAk/iwc4MZGYFm8mnPwHHfUK/dO8pKURyHcG3FNsfEjssYE7Qnpkz
GzLujbcGDL7Ufq84UVk3hGOe9Zqm7p6rpTBN44hLAQKBgQD6FJgOldDIwIJdinGX
B+k9ODTs7sJGHhSEbQaOUcliq05DFXDH56PbgV48zZ5tJjG2d04jHpw5pkPo3ulG
GKIFe+O61sgp7cJ/FY+BCF/bvn+xYw1pOvA62wCqyvcfUljceqmMKmVyZePFm1D3
EglKKcRfvD6vn/kyuK6pEenhCQKBgQDAP4pTOIvehZ02bKyZ9ifh885um2nJ+C1M
9SI+ypIUpsWGypFmiAdGc1wMpKhKgKC8ZEl1xKdjNmRLFNlpbcr1ny7D7FdvwI94
1yEY1bJPrUFbXdWokn6HMgOq9ysVCdc3ApM371R+WF3AcC/8SvEUGzTXxJ8sGHfh
tUDec+sY7QKBgQCRYHtsrybqLQ8b9alG1TB/iDcsLTf+runaec6/2Ueq9k7OrJ4d
d8lHh5MS4a1hYjywB/cCb379/Gup6jvNpfA6I+Uk7kr6JN9WJWCA8C9ZfQqaQiy/
qaWRcVKX9tll+ebydNQvSU4kDJs2eq28k12XIWSpCrOeQO8Kz1Wpr2I4kQKBgH1N
7P7pMGFNfXbnxmhjhQNFQhvduEooNH6gmD2NE0HaoYyFo9fMedF1h13GRNqqlBm2
1Bqqnt+PqDc3061gHpWRt42EEkmInPsKXUwunRZJuvuuYYCKW2YLN1DL4YzI6Tm1
t/cRS2U+e3zeoqgywId2ZC7uvUCkgh7fYPSdYXLRAoGAewflDOdwWVyhrziFiB05
W/A4iv8qxmexNQ+PzYryrV0dxS9J5cQiXdv327tCHzFwWEIXsrbD0+lMy/ATTDnd
TsDMni+zjg7UxH2k1IHA8XuXaRWhuXNxpZ0WRXy5Fajy7C+UcpucJl/959uWjX+O
LGxI1AyMRRYWlk17of8h83o=
-----END PRIVATE KEY-----
"""


@pytest.fixture(scope='module')
def cli() -> DcosCli:
    return DcosCli.new_cli()


class TestSecrets:
    def test_secrets(
        self,
        artifact_path: Path,
        docker_backend: Docker,
        license_key_contents: str,
        request: SubRequest,
        log_dir: Path,
        superuser_username: str,
        superuser_password: str,
        cli: DcosCli,
        kind_path: Path,
        kubectl_path: Path,
        tmp_path: Path,
    ):
        config = {
            'superuser_username': superuser_username,
            'superuser_password_hash': sha512_crypt.hash(superuser_password),
            'security': 'strict',
            'fault_domain_enabled': 'false',
            'license_key_contents': license_key_contents,
        }

        with Cluster(cluster_backend=docker_backend, agents=0, public_agents=0) as cluster:
            master = next(iter(cluster.masters))
            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config={
                    **cluster.base_config,
                    **config,
                },
                output=Output.LOG_AND_CAPTURE,
                ip_detect_path=docker_backend.ip_detect_path,
            )

            wait_for_dcos_ee(
                cluster=cluster,
                superuser_username=superuser_username,
                superuser_password=superuser_password,
                request=request,
                log_dir=log_dir,
            )

            master_url = 'https://' + str(master.public_ip_address)

            cli.setup_enterprise(master_url, superuser_username, superuser_password)

            # Add secrets to DC/OS

            # key1: value1
            value1 = 'value1'
            cli.exec_command(
                ['dcos', 'security', 'secrets', 'create', '--value', value1, 'key1']
            )

            # folder/key2: value2
            value2 = 'value2\n'
            secret2 = tmp_path / 'file2'
            secret2.write_text(value2)
            cli.exec_command([
                'dcos',
                'security',
                'secrets',
                'create',
                '--text-file',
                str(secret2),
                'folder/key2'
            ])

            # folder/key3: value3 (binary)
            value3 = b'value\x85\xff3'
            secret3 = tmp_path / 'file3'
            secret3.write_bytes(value3)
            cli.exec_command([
                'dcos', 'security', 'secrets', 'create', '--file', str(secret3), 'folder/key3'
            ])

            # folder/sub/key4: sa-account-details
            secret4 = tmp_path / 'file.pem'
            secret4.write_text(PRIVATE_KEY)
            cli.exec_command([
                'dcos',
                'security',
                'secrets',
                'create-sa-secret',
                str(secret4),
                'dcos-service',
                'folder/sub/key4'
            ])

            # The DC/OS Secrets Service permits a secret to exist at the same path as a folder.
            # key5: value5
            value5 = 'value5'
            cli.exec_command(
                ['dcos', 'security', 'secrets', 'create', '--value', value5, 'folder/sub']
            )

            # Setup DCOSSecretsService client

            dcos_cluster_id = backup.get_dcos_cluster_id(cli.path)
            url = backup.get_dcos_url(cli.path)
            token = backup.get_dcos_token(cli.path)

            s = backup.DCOSSecretsService(url, token, False)

            # `list` returns all keys below the folder
            response = s.list('')
            assert response == [
                'folder/key2', 'folder/key3', 'folder/sub', 'folder/sub/key4', 'key1'
            ]

            response = s.list('folder')
            assert response == ['key2', 'key3', 'sub', 'sub/key4']

            # When there is a secret and a folder at the same path, `list` returns the secrets
            # under the folder.
            response = s.list('folder/sub')
            assert response == ['key4']

            response = s.list('folder/sub/key4')
            assert response == []

            response = s.list('fold')
            assert response == []

            response = s.list('not/a/folder')
            assert response == []

            # `get` returns value of a single secret
            response = s.get('', 'key1')
            assert response['path'] == ''
            assert response['key'] == 'key1'
            assert response['type'] == 'text'
            assert base64.b64decode(response['value']).decode('utf-8') == value1

            response = s.get('', 'folder/key2')
            assert response['path'] == ''
            assert response['key'] == 'folder/key2'
            assert response['type'] == 'text'
            assert base64.b64decode(response['value']).decode('utf-8') == value2

            response = s.get('', 'folder/key3')
            assert response['path'] == ''
            assert response['key'] == 'folder/key3'
            assert response['type'] == 'binary'
            assert base64.b64decode(response['value']) == value3

            response = s.get('', 'folder/sub/key4')
            assert response['path'] == ''
            assert response['key'] == 'folder/sub/key4'
            assert response['type'] == 'text'
            assert json.loads(base64.b64decode(response['value'])) == {
                "login_endpoint": "https://leader.mesos/acs/api/v1/auth/login",
                "private_key": PRIVATE_KEY,
                "scheme": "RS256",
                "uid": "dcos-service"
            }

            response = s.get('', 'folder/sub')
            assert response['path'] == ''
            assert response['key'] == 'folder/sub'
            assert response['type'] == 'text'
            assert base64.b64decode(response['value']).decode('utf-8') == value5

            response = s.get('folder', 'key2')
            assert response['path'] == 'folder'
            assert response['key'] == 'key2'
            assert response['type'] == 'text'
            assert base64.b64decode(response['value']).decode('utf-8') == value2

            response = s.get('folder', 'key3')
            assert response['path'] == 'folder'
            assert response['key'] == 'key3'
            assert response['type'] == 'binary'
            assert base64.b64decode(response['value']) == value3

            response = s.get('folder', 'sub/key4')
            assert response['path'] == 'folder'
            assert response['key'] == 'sub/key4'
            assert response['type'] == 'text'
            assert json.loads(base64.b64decode(response['value'])) == {
                "login_endpoint": "https://leader.mesos/acs/api/v1/auth/login",
                "private_key": PRIVATE_KEY,
                "scheme": "RS256",
                "uid": "dcos-service"
            }

            response = s.get('folder/sub', 'key4')
            assert response['path'] == 'folder/sub'
            assert response['key'] == 'key4'
            assert response['type'] == 'text'
            assert json.loads(base64.b64decode(response['value'])) == {
                "login_endpoint": "https://leader.mesos/acs/api/v1/auth/login",
                "private_key": PRIVATE_KEY,
                "scheme": "RS256",
                "uid": "dcos-service"
            }

            # Trying to `get` a folder raises 404
            with pytest.raises(requests.HTTPError) as exception:
                response = s.get('folder', '')
            assert exception.value.response.status_code == 404

            # Non-existent secret raises 404
            with pytest.raises(requests.HTTPError) as exception:
                s.get('not/a/path', '')
            assert exception.value.response.status_code == 404

            # Test backup of DC/OS secrets

            dcosfile1 = tmp_path / 'output-1'
            backup.run(['--no-verify', '--output', str(dcosfile1)])
            assert stat.S_IMODE(dcosfile1.stat().st_mode) == 0o600
            with dcosfile1.open() as f:
                response = json.load(f)
            keys = set(s['key'] for s in response['secrets'])
            assert keys == {'key1', 'folder/key2', 'folder/key3', 'folder/sub', 'folder/sub/key4'}

            dcosfile2 = tmp_path / 'output-2'
            backup.run(['--no-verify', '--path', 'folder', '--output', str(dcosfile2)])
            assert stat.S_IMODE(dcosfile2.stat().st_mode) == 0o600
            with dcosfile2.open() as f:
                response = json.load(f)
            keys = set(s['key'] for s in response['secrets'])
            assert keys == {'key2', 'key3', 'sub', 'sub/key4'}

            # When backing up a path that is a secret and a folder, only the secrets under the
            # folder are exported, not the secret at the named path.
            dcosfile3 = tmp_path / 'output-3'
            backup.run(['--no-verify', '--path', 'folder/sub', '--output', str(dcosfile3)])
            assert stat.S_IMODE(dcosfile3.stat().st_mode) == 0o600
            with dcosfile3.open() as f:
                response = json.load(f)
            keys = set(s['key'] for s in response['secrets'])
            assert keys == {'key4'}

            # The command will not work without a CA flag as the test DC/OS cluster CA is not in the
            # system CA bundle.
            with pytest.raises(requests.exceptions.SSLError):
                backup.run(
                    [
                        '--path', 'folder/sub/key4',
                        '--output', str(dcosfile3)
                    ]
                )

            # Download the CA certificate for the cluster to verify subsequent connections. Since we
            # don't yet have the CA certificate, this request cannot be verified (and hence is
            # insecure).
            r = requests.get(url + '/ca/dcos-ca.crt', verify=False)
            r.raise_for_status()
            cert = r.content
            ca_path = tmp_path / 'ca_cert'
            ca_path.write_bytes(cert)

            dcosfile4 = tmp_path / 'output-4'
            backup.run(
                [
                    '--ca-file', str(ca_path),
                    '--path', 'folder/sub/key4',
                    '--output', str(dcosfile4)
                ]
            )
            assert stat.S_IMODE(dcosfile4.stat().st_mode) == 0o600
            with dcosfile4.open() as f:
                response = json.load(f)['secrets']
            assert len(response) == 1
            s = response[0]
            assert s['path'] == 'folder/sub'
            assert s['key'] == 'key4'

        # Test migration from DC/OS file to K8s file

        # Multiple secrets
        k8s_secret_name = 'mysecrets'
        k8sfile = tmp_path / 'output-1k'
        migrate.run([
            '--input', str(dcosfile1), '--output', str(k8sfile), '--name', k8s_secret_name
        ])
        assert stat.S_IMODE(k8sfile.stat().st_mode) == 0o600
        with k8sfile.open() as f:
            response = json.load(f)
        assert response['metadata']['labels'][DCOS_PREFIX + '/dcos-cluster-id'] == dcos_cluster_id
        assert sorted(
            json.loads(response['metadata']['annotations'][DCOS_PREFIX + '/dcos-secret']).items()
        ) == [
            ('folder/key2', 'folder.key2'),
            ('folder/key3', 'folder.key3'),
            ('folder/sub', 'folder.sub'),
            ('folder/sub/key4', 'folder.sub.key4'),
            ('key1', 'key1'),
        ]
        keys = response['data'].keys()
        assert keys == {'key1', 'folder.key2', 'folder.key3', 'folder.sub', 'folder.sub.key4'}

        # Single secret
        k8s_secret_name_4 = 'mysecrets4'
        k8sfile_4 = tmp_path / 'output-4k'
        migrate.run([
            '--input', str(dcosfile4), '--output', str(k8sfile_4), '--name', k8s_secret_name_4
        ])
        assert stat.S_IMODE(k8sfile_4.stat().st_mode) == 0o600
        with k8sfile_4.open() as f:
            response = json.load(f)
        assert response['metadata']['labels'][DCOS_PREFIX + '/dcos-cluster-id'] == dcos_cluster_id
        assert json.loads(response['metadata']['annotations'][DCOS_PREFIX + '/dcos-secret']) == {
            'folder/sub/key4': 'key4'
        }
        keys = response['data'].keys()
        assert keys == {'key4'}

        # Test that migrated file is valid input to K8s

        kind_name = ''.join(random.choice(string.ascii_lowercase) for x in range(4))
        kind_context = 'kind-{}'.format(kind_name)

        kubeconfig_path = tmp_path / 'kubeconfig'
        subprocess.run([
            str(kind_path),
            'create',
            'cluster',
            '--name',
            kind_name,
            '--kubeconfig',
            str(kubeconfig_path)
        ])
        try:
            p = subprocess.run(
                [
                    str(kubectl_path),
                    '--kubeconfig',
                    str(kubeconfig_path),
                    '--context',
                    kind_context,
                    'apply',
                    '--filename',
                    str(k8sfile)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True
            )
            assert b'secret/mysecrets created' in p.stdout

            # Check that the Secret resource has the expected keys and values.
            p = subprocess.run(
                [
                    str(kubectl_path),
                    '--kubeconfig',
                    str(kubeconfig_path),
                    '--context',
                    kind_context,
                    'get',
                    'secret',
                    k8s_secret_name,
                    '-o',
                    'jsonpath={.data.key1}'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True
            )
            assert base64.b64decode(p.stdout.decode('ascii')).decode('utf-8') == value1

            # Check that we can search for secrets by cluster id and find the original DC/OS path
            # for a secret.
            p = subprocess.run(
                [
                    str(kubectl_path),
                    '--kubeconfig',
                    str(kubeconfig_path),
                    '--context',
                    kind_context,
                    'get',
                    'secrets',
                    '-l',
                    '{}/dcos-cluster-id={}'.format(DCOS_PREFIX, dcos_cluster_id),
                    '-o',
                    'json'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True
            )
            items = json.loads(p.stdout)['items']
            assert len(items) == 1
            reverse_map = json.loads(
                items[0]['metadata']['annotations'][DCOS_PREFIX + '/dcos-secret']
            )
            assert reverse_map['folder/sub/key4'] == 'folder.sub.key4'
        finally:
            subprocess.run([
                str(kind_path), 'delete', 'cluster', '--kubeconfig', str(kubeconfig_path)
            ])
