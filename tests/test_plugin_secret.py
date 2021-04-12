import pytest
import requests_mock
import base64
import json
from dcos import config
from dcos_migrate.system import DCOSClient, ManifestList, BackupList, Backup
from dcos_migrate.plugins.secret import SecretPlugin

adapter = requests_mock.Adapter()


@pytest.fixture
def conf():
    return config.Toml({
        "core": {
            "dcos_url": "mock://test.cluster.mesos",
            "ssl_verify": "false",
            "dcos_acs_token": "im-a-fake-token"
        },
        "cluster": {
            "name": "test-cluster"
        }
    })


@requests_mock.Mocker(kw='mock')
def test_secret_backup(conf, **kwargs):
    kwargs['mock'].register_uri('GET',
                                'mock://test.cluster.mesos/secrets/v1/secret/default/?list=true',
                                json={"array": ["foo/secret"]},
                                headers={'content-type': 'application/json'})
    kwargs['mock'].register_uri('GET',
                                'mock://test.cluster.mesos/secrets/v1/secret/default/foo/secret',
                                json={"value": "21a692c6286114e51e28510242eafc4010c46fe0"},
                                headers={'content-type': 'application/json'})

    client = DCOSClient(toml_config=conf)

    s = SecretPlugin()
    backup = s.backup(client)

    assert len(backup) == 1
    assert backup[0].data['value'] == base64.b64encode(
        "21a692c6286114e51e28510242eafc4010c46fe0".encode('utf-8')).decode('ascii')


def test_secret_migrate():
    with open('tests/examples/simpleSecret.json') as json_file:
        data = json.load(json_file)

        assert data['key'] is not None

        bl = BackupList()
        bl.append(Backup(pluginName='secret', backupName='foo.bar', data=data))

        s = SecretPlugin()

        ml = s.migrate(backupList=bl, manifestList=ManifestList())

        assert len(ml) == 1
        assert ml[0][0].data['foo.bar'] == 'Rk9PQkFS'
