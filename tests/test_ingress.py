#

import os
import json

from kubernetes import client
import pytest

from dcos_migrate.plugins.ingress import edgelb
from dcos_migrate.plugins.ingress import migrator
from dcos_migrate.plugins.ingress import plugin
from dcos_migrate import system

TEST_DIR = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def pool(request):
    file = request.param

    if file[-5:] != ".json":
        file = "{}.json".format(file)

    path = os.path.join(TEST_DIR, "examples", "edgelb", file)
    with open(path) as fp:
        return json.load(fp)


class TestEdgeLB(object):
    @pytest.mark.parametrize("pool", ("sample1", "sample0"), indirect=True)
    def test_parse_pool(self, pool):
        with pytest.warns(None) as warnings:
            assert edgelb.parse_pool(pool)
        assert not warnings, [str(warning.message) for warning in warnings]

    @pytest.mark.parametrize("pool", ("sample-mesos-framework", ), indirect=True)
    def test_parse_tcp(self, pool):
        with pytest.warns(None) as warnings:
            p = edgelb.parse_pool(pool)

        assert p == {
            "autoCertificate": False,
            "autopool": False,
            "backends": {
                "stats-backend": {
                    "balance": "roundrobin",
                    "service": {
                        "name": "UNKNOWN",
                        "port": "9090"
                    },
                }
            },
            "frontends": {
                1025: {
                    "certificates": [],
                    "default_backend": "stats-backend",
                    "name": "frontend_0.0.0.0_1025",
                    "port": 1025,
                    "protocol": "TCP",
                    "rules": [],
                }
            },
            "name": "framework-pool",
            "namespace": None,
            "secrets": [],
        }

        messages = [str(warning.message) for warning in warnings]
        assert any(m for m in messages if "portName" in m), messages

    @pytest.mark.parametrize("pool", ("pool-http", ), indirect=True)
    def test_parse_http(self, pool):
        with pytest.warns(None) as warnings:
            p = edgelb.parse_pool(pool)

        assert p == {
            "autoCertificate": False,
            "autopool": False,
            "backends": {
                "bridge-nginx": {
                    "balance": "roundrobin",
                    "service": {
                        "name": "bridge-nginx",
                        "port": "web"
                    },
                },
                "host-httpd": {
                    "balance": "roundrobin",
                    "service": {
                        "name": "host-httpd",
                        "port": "web"
                    },
                },
            },
            "frontends": {
                80: {
                    "certificates": [],
                    "default_backend": "bridge-nginx",
                    "name": "frontend_0.0.0.0_80",
                    "port": 80,
                    "protocol": "HTTP",
                    "rules": [{
                        "backend": "host-httpd",
                        "path": "/httpd/.*"
                    }],
                }
            },
            "name": "test-http-pool",
            "namespace": None,
            "secrets": [],
        }

        assert not warnings, [str(warning.message) for warning in warnings]


class TestMigrator(object):
    @pytest.mark.parametrize("pool", ("sample1", "sample0"), indirect=True)
    def test_parse_pool(self, pool):
        with pytest.warns(None) as warnings:
            assert any(migrator.migrate(edgelb.parse_pool(pool)))

        name = pool.get("name")

        messages = [str(warning.message) for warning in warnings]
        if name == "sample0":
            assert any("80/443" in m for m in messages), messages
        else:
            assert not warnings, messages

    @pytest.mark.parametrize("pool", ("sample-mesos-framework", ), indirect=True)
    def test_parse_tcp(self, pool):
        bl = system.BackupList()

        with pytest.warns(None):
            parsed_pool = edgelb.parse_pool(pool)

            assert parsed_pool
            backup = system.Backup(
                plugin.EdgeLBPlugin.plugin_name,
                system.Backup.renderBackupName(pool["name"]),
                parsed_pool,
            )
            bl.append(backup)

        kc = client.ApiClient()
        ml = plugin.EdgeLBPlugin().migrate(bl, system.ManifestList())
        assert ml

        for m in ml.manifests("ingress"):
            assert m
            doc = kc.sanitize_for_serialization(m[0])
            assert doc == {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "annotations": {},
                    "name": "framework-pool",
                },
                "spec": {
                    "ports": [{
                        "port": 1025,
                        "protocol": "TCP",
                        "targetPort": 0
                    }],
                    "selector": {
                        "app": "UNKNOWN"
                    },
                    "type": "LoadBalancer",
                },
            }

    @pytest.mark.parametrize("pool", ("pool-http", ), indirect=True)
    def test_parse_http(self, pool):
        bl = system.BackupList()

        with pytest.warns(None):
            parsed_pool = edgelb.parse_pool(pool)

            assert parsed_pool
            backup = system.Backup(
                plugin.EdgeLBPlugin.plugin_name,
                system.Backup.renderBackupName(pool["name"]),
                parsed_pool,
            )
            bl.append(backup)

        kc = client.ApiClient()
        ml = plugin.EdgeLBPlugin().migrate(bl, system.ManifestList())
        assert ml

        for m in ml.manifests("ingress"):
            assert m
            doc = kc.sanitize_for_serialization(m[0])
            assert doc == {
                "apiVersion": "extensions/v1beta1",
                "kind": "Ingress",
                "metadata": {
                    "annotations": {
                        "kubernetes.io/ingress.class": "traefik"
                    },
                    "name": "test-http-pool",
                },
                "spec": {
                    "rules": [{
                        "http": {
                            "paths": [{
                                "backend": {
                                    "serviceName": "host-httpd",
                                    "servicePort": "web",
                                },
                                "path": "/httpd/.*",
                            }]
                        }
                    }]
                },
            }
