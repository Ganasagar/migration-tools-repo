from dcos_migrate.system import ManifestList, Manifest
from kubernetes.client.models import V1ObjectMeta, V1Secret
import pytest


def create_example_list_manifest(dir: str) -> ManifestList:
    list = ManifestList(path=str(dir))

    p = "testPlugin"
    b = "foobar"
    metadata = V1ObjectMeta(name="secret1")
    sec = V1Secret(metadata=metadata, kind="Secret", api_version="v1")
    sec.data = {
        "secret1": "Zm9vYmFy"
    }
    d = [sec]
    list.append(Manifest(pluginName=p,
                         manifestName=b, data=d))

    list.store()
    return list, p, b, d


def test_load():
    ml = ManifestList(path='tests/examples/simpleWithSecret')
    ml.load()

    secrets = [{'secret1': 'Zm9vYmFy'}, {'test.secret2': 'YmF6'}]
    assert ml is not None
    assert len(ml) == 2
    for m in ml:
        assert m is not None
        assert len(m) > 0
        for s in m:
            assert s.kind == "Secret"
            assert s.api_version == "v1"
            assert s.data is not None
            assert s.data in secrets
            # Remove found secrets from the list to ensure they appear only once
            secrets.remove(s.data)
    # We found all the expected secrets
    assert len(secrets) == 0


def test_load_manifest(tmpdir):
    dir = tmpdir.mkdir("test")
    list, p, b, d = create_example_list_manifest(str(dir))

    list2 = ManifestList(path=str(dir))
    list2.load()

    # we expect different objects
    assert list == list2
    # but the same amount

    assert len(list) == len(list2)
    # and data
    assert list[0][0].data == list2[0][0].data


def test_manifest():
    ml = ManifestList(path='tests/examples/simpleWithSecret')
    ml.load()

    assert len(ml) == 2

    sec2 = ml.manifest(pluginName="secret", manifestName="test.secret2")

    assert sec2 is not None
    assert len(sec2) == 1
    assert sec2[0].metadata.name == "test.secret2"
