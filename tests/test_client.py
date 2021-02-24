import pytest
import requests_mock
import dcos
from dcos.errors import DCOSAuthenticationException
from dcos_migrate.system.client import DCOSClient

adapter = requests_mock.Adapter()


@pytest.fixture
def conf():
    return {
        "core": {
            "dcos_url": "mock://test.cluster.mesos",
            "ssl_verify": "false",
            "dcos_acs_token": "im-a-fake-token"
        },
        "cluster": {
            "name": "test-cluster"
        }
    }


@requests_mock.Mocker(kw='mock')
def test_client_request(conf, **kwargs):
    kwargs['mock'].get('mock://test.cluster.mesos/foo',
                       text='{"msg": "bar"}')

    client = DCOSClient(toml_config=dcos.config.Toml(conf))

    url = client.full_dcos_url("foo")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json() == {'msg': 'bar'}


@requests_mock.Mocker(kw='mock')
def test_client_request_authentication(conf, **kwargs):
    kwargs['mock'].get('mock://test.cluster.mesos/foo',
                       headers={"Authorization": "token=im-a-fake-token"})

    client = DCOSClient(toml_config=dcos.config.Toml(conf))
    invalid = conf
    invalid["core"]["dcos_acs_token"] = "foobar"
    client_invalid = DCOSClient(toml_config=dcos.config.Toml(invalid))
    resp = client.get(client.full_dcos_url("foo"))
    assert resp.status_code == 200

    kwargs['mock'].get('mock://test.cluster.mesos/foo',
                       status_code=401)

    with pytest.raises(DCOSAuthenticationException):
        client_invalid.get(client.full_dcos_url("foo"))
