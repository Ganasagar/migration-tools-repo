import pytest

from dcos_migrate.plugins.marathon import app_translator

from .common import DummyAppSecretMapping

EMPTY_SETTINGS = app_translator.Settings(
    app_translator.ContainerDefaults(
        image="busybox",
        working_dir=None,
    ),
    app_secret_mapping=DummyAppSecretMapping(),
)


def test_command_ready_with_all_fields_set():
    app = {
        "id":
        "/ready",
        "readinessChecks": [{
            "name": "readinessCheck",
            "protocol": "HTTPS",
            "path": "/ready",
            "portName": "main",
            "intervalSeconds": 30,
            "timeoutSeconds": 20,
            "httpStatusCodesForReady": [200],
            "preserveLastResponse": False
        }],
        "container": {
            "portMappings": [{
                "containerPort": 3000,
                "hostPort": 0,
                "labels": {},
                "name": "main",
                "protocol": "tcp",
                "servicePort": 10000
            }]
        }
    }

    translated = app_translator.translate_app(app, EMPTY_SETTINGS)

    container = translated.deployment['spec']['template']['spec']['containers'][0]

    assert 'readinessProbe' in container
    assert container['readinessProbe'] == {
        "timeoutSeconds": 20,
        "periodSeconds": 30,
        "httpGet": {
            "path": "/ready",
            "port": "main",
            "scheme": "HTTPS"
        }
    }
