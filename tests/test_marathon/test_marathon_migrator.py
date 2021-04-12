from dcos_migrate.plugins.marathon import MarathonMigrator, NodeLabelTracker
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

        assert len(m.manifest) == 3

        assert mres is not None
        app_id = 'group1.predictionio-server'
        app_label = 'group1-predictionio-server'
        assert m.manifest[0].metadata.name == app_id
        assert m.manifest[1].metadata.name == app_label
        assert m.manifest[2].metadata.name == 'marathonsecret-group1.predictionio-server'

        assert m.manifest[0].metadata.labels['app'] == app_label
        assert m.manifest[0].spec.template.spec.containers[0].env[
            0].value_from.secret_key_ref.name == "marathonsecret-group1.predictionio-server"
        assert m.manifest[0].spec.template.spec.containers[0].env[0].value_from.secret_key_ref.key == "secret1"
        assert m.manifest[0].spec.template.spec.containers[0].env[
            1].value_from.secret_key_ref.name == "marathonsecret-group1.predictionio-server"
        assert m.manifest[0].spec.template.spec.containers[0].env[1].value_from.secret_key_ref.key == "test.secret2"

        assert m.manifest[1].kind == 'Service'
        assert m.manifest[1].spec.selector['app'] == app_label

        assert 'secret1' in m.manifest[2].data
        assert 'test.secret2' in m.manifest[2].data


def test_docker_pull_config_secret():
    pull_config_str = '{"auths":{"example.com":{"username":"jd","password":"deadbeef",'\
                      '"email":"jdoe@example.com","auth":"f00BA7"}}}'

    migrated_dcos_secret = V1Secret(kind='Secret',
                                    api_version='v1',
                                    metadata=V1ObjectMeta(name='nothing-depends-on-this-name'),
                                    data={'nothing-depends-on-the-name-of-this-key': pull_config_str})

    input_manifest_list = ManifestList()
    input_manifest_list.append(
        Manifest(pluginName="secret", manifestName="foo.docker-c_nfig", data=[migrated_dcos_secret]))

    app = {
        "id": "/foo/barify",
        "container": {
            "docker": {
                "pullConfig": {
                    "secret": "pull-config"
                }
            }
        },
        "env": {
            "BAR": {
                "secret": "pull-config"
            }
        },  # See the NOTE below
        "secrets": {
            "pull-config": {
                "source": "/foo/docker-c@nfig"
            },
            "unused": {
                "source": "unused"
            },
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


def test_constraint_node_labels():
    apps = [{
        "id": "/foo",
        "constraints": [["@hostname", "IS", "10.123.45.67"], ["baz", "UNIQUE"]]
    }, {
        "id": "/bar",
        "constraints": [["@zone", "LIKE", "antarctic1"], ["baz", "UNIQUE"]]
    }]

    tracker = NodeLabelTracker()

    for app in apps:
        MarathonMigrator(node_label_tracker=tracker, object=app).migrate()

    apps_by_label = tracker.get_apps_by_label()
    assert apps_by_label == {
        "baz": {'/foo', '/bar'},
        "topology.kubernetes.io/zone": {'/bar'},
        "dcos.io/former-dcos-hostname": {'/foo'}
    }


def test_dcos_apps_are_skipped():
    app = {"id": "/foo", "labels": {"DCOS_PACKAGE_FRAMEWORK_NAME": "dcos-foo"}}

    migrator = MarathonMigrator(object=app)
    manifest = migrator.migrate()
    assert not manifest
