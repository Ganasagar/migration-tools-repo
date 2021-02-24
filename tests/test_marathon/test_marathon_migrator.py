from dcos_migrate.plugins.marathon import MarathonMigrator
from dcos_migrate.system import Manifest, ManifestList

from kubernetes.client.models import V1Deployment, V1ObjectMeta, V1Secret  # type: ignore

import json
import pytest


def test_simple():
    with open('tests/examples/simple.json') as json_file:
        data = json.load(json_file)

        m = MarathonMigrator(object=data)

        mres = m.migrate()

        assert mres is not None
        # assert m.manifest[0]['metadata']['name'] == 'predictionio-server.group1'
        assert m.manifest[0].metadata.name == 'group1.predictionio-server'


@pytest.mark.xfail
def test_simple_portmapping():
    with open('tests/examples/simplePortmapping.json') as json_file:
        data = json.load(json_file)

        m = MarathonMigrator(object=data)

        mres = m.migrate()

        assert mres is not None
        # assert m.manifest[0]['metadata']['name'] == 'predictionio-server.group1'
        assert m.manifest[0]['metadata']['name'] == 'group1.predictionio-server'


def test_simple_with_secret():
    ml = ManifestList(path='tests/examples/simpleWithSecret')
    ml.load()

    assert len(ml) == 2
    with open('tests/examples/simpleWithSecret.json') as json_file:
        data = json.load(json_file)

        m = MarathonMigrator(object=data, manifest_list=ml)

        mres = m.migrate()

        assert len(m.manifest) == 2

        assert mres is not None
        # assert m.manifest[0]['metadata']['name'] == 'predictionio-server.group1'
        assert m.manifest[0].metadata.name == 'group1.predictionio-server'
        assert m.manifest[1].metadata.name == 'marathonsecret-group1.predictionio-server'

        assert m.manifest[0].spec.template.spec.containers[0].env[
            0].value_from.secret_key_ref.name == "marathonsecret-group1.predictionio-server"
        assert m.manifest[0].spec.template.spec.containers[0].env[
            0].value_from.secret_key_ref.key == "secret1"
        assert m.manifest[0].spec.template.spec.containers[0].env[
            1].value_from.secret_key_ref.name == "marathonsecret-group1.predictionio-server"
        assert m.manifest[0].spec.template.spec.containers[0].env[
            1].value_from.secret_key_ref.key == "test.secret2"

        assert 'secret1' in m.manifest[1].data
        assert 'test.secret2' in m.manifest[1].data


def test_docker_pull_config_secret():
    pull_config_str = '{"auths":{"example.com":{"username":"jd","password":"deadbeef",'\
                      '"email":"jdoe@example.com","auth":"f00BA7"}}}'

    migrated_dcos_secret = V1Secret(
        kind='Secret',
        api_version='v1',
        metadata=V1ObjectMeta(name='nothing-depends-on-this-name'),
        data={'nothing-depends-on-the-name-of-this-key': pull_config_str}
    )

    input_manifest_list = ManifestList()
    input_manifest_list.append(Manifest(
        pluginName="secret",
        manifestName="foo.docker-c_nfig",
        data=[migrated_dcos_secret])
    )

    app = {
        "id": "/foo/barify",
        "container": {"docker": {"pullConfig": {"secret": "pull-config"}}},
        "env": {"BAR": {"secret": "pull-config"}}, # See the NOTE below
        "secrets": {
            "pull-config": {"source": "/foo/docker-c@nfig"},
            "unused": {"source": "unused"},
        },
    }

    migrator = MarathonMigrator(object=app, manifest_list=input_manifest_list)
    manifest = migrator.migrate()

    # NOTE: Thit test expects that two secrets will be created:
    # one for the image pull config and another for everything else.
    # This might be not the optimal migration startegy.
    [deployment] = [m for m in manifest if isinstance(m, V1Deployment)]

    [pull_secret] = [m for m in manifest \
        if isinstance(m, V1Secret) and m.type == "kubernetes.io/dockerconfigjson"]

    [generic_secret] = [m for m in manifest \
        if isinstance(m, V1Secret) and m.type != "kubernetes.io/dockerconfigjson"]


    assert deployment.spec.template.spec.image_pull_secrets[0].name == pull_secret.metadata.name

    assert pull_secret.data[".dockerconfigjson"] == pull_config_str

    assert generic_secret.data["foo.docker-c_nfig"] == pull_config_str
