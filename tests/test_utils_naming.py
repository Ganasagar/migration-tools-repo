import pytest
from dcos_migrate.utils import make_label, make_subdomain, dnsify, namespace_path


@pytest.mark.parametrize("path_name, expected_name", [
    ("", "x"),
    ("foo", "foo"),
    ("foo/bar", "foo-bar"),
    ("foo!bar/baz", "foo-bar-baz"),
    (
        "storage/tls-6EXBIFNI3ADKCHAKEKFSO7RA6SZO4WAUO5JMXMFN5LS5DXA5N23A-private-key",
        "storage-tls-6EXBIFNI3ADKCHAKEKFSO7RA6SZO4WAUO5JMXMFN5LS5DXA5N23"
    ),
    ("==", 'x0'),
])
def test_make_label(path_name, expected_name):
    assert make_label(path_name) == expected_name


@pytest.mark.parametrize("path_name, expected_name", [
    ("", ""),
    ("foo", "foo"),
    ("foo/bar", "foo.bar"),
    ("foo!bar/baz", "foo-bar.baz"),
    (
        "storage/tls-6EXBIFNI3ADKCHAKEKFSO7RA6SZO4WAUO5JMXMFN5LS5DXA5N23A-private-key",
        "storage.tls-6exbifni3adkchakekfso7ra6szo4wauo5jmxmfn5ls5dxa5n23a-privat.e-key"
    ),
    ("==", 'x--0'),
])
def test_make_subdomain(path_name, expected_name):
    assert make_subdomain(path_name.split('/')) == expected_name


@pytest.mark.parametrize("path_name, expected_name", [
    ("", ""),
    ("foo", "foo"),
    ("foo/bar", "foo.bar"),
    ("foo!bar/baz", "foo_bar.baz"),
    (
        "storage/tls-6EXBIFNI3ADKCHAKEKFSO7RA6SZO4WAUO5JMXMFN5LS5DXA5N23A-private-key",
        "storage.tls-6EXBIFNI3ADKCHAKEKFSO7RA6SZO4WAUO5JMXMFN5LS5DXA5N23A-private-key"
    ),
    ("==", '__'),
])
def test_dnsify(path_name, expected_name):
    assert dnsify(path_name) == expected_name


@pytest.mark.parametrize("name, namespaced_name", [
    ("foo", "migration.dcos.d2iq.com/foo"),
])
def test_namespace_path(name, namespaced_name):
    assert namespace_path(name) == namespaced_name
