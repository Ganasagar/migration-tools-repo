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


def test_command_health_check_with_all_fields_set():
    app = {
        "id":
        "/healthy",
        "healthChecks": [{
            "protocol": "COMMAND",
            "command": {
                "value": "exit 0"
            },
            "gracePeriodSeconds": 123,
            "intervalSeconds": 45,
            "timeoutSeconds": 99,
            "maxConsecutiveFailures": 333
        }],
    }

    translated = app_translator.translate_app(app, EMPTY_SETTINGS)

    container = translated.deployment['spec']['template']['spec']['containers'][0]

    assert 'livenessProbe' in container
    assert container['livenessProbe'] == {
        "failureThreshold": 333,
        "timeoutSeconds": 99,
        "periodSeconds": 45,
        "initialDelaySeconds": 123,
        "exec": {
            "command": ["/bin/sh", "-c", "exit 0"]
        }
    }


def test_second_health_check_dropped_warning():
    """
    Tests that only the first health check is converted into a liveness probe,
    and a warning is emitted for all the other health checks.
    """
    app = {
        "id":
        "/twice-healthy",
        "healthChecks": [
            {
                "protocol": "COMMAND",
                "command": {
                    "value": "exit 0"
                }
            },
            {
                "protocol": "COMMAND",
                "command": {
                    "value": "sleep 1"
                }
            },
        ],
    }

    translated = app_translator.translate_app(app, EMPTY_SETTINGS)

    assert any("dropped health check" in w.lower() for w in translated.warnings)
    assert translated.deployment['spec']['template']['spec']['containers'][0]['livenessProbe']['exec']['command'] ==\
        ["/bin/sh", "-c", "exit 0"]


@pytest.mark.parametrize("health_check,expected_action_key,expected_action", [
    (
        {
            "protocol": "HTTPS",
            "port": 10445,
            "path": "/status"
        },
        "httpGet",
        {
            "path": "/status",
            "port": 10445,
            "scheme": "HTTPS"
        },
    ),
    (
        {
            "protocol": "MESOS_HTTPS",
            "port": 9443,
            "path": "/status"
        },
        "httpGet",
        {
            "path": "/status",
            "port": 9443,
            "scheme": "HTTPS"
        },
    ),
    (
        {
            "protocol": "HTTP",
            "port": 85,
            "path": "/healthz"
        },
        "httpGet",
        {
            "path": "/healthz",
            "port": 85,
            "scheme": "HTTP"
        },
    ),
    (
        {
            "protocol": "MESOS_HTTP",
            "port": 60080,
            "path": "/healthz"
        },
        "httpGet",
        {
            "path": "/healthz",
            "port": 60080,
            "scheme": "HTTP"
        },
    ),
    ({
        "protocol": "TCP",
        "port": 123
    }, "tcpSocket", {
        "port": 123
    }),
    ({
        "protocol": "MESOS_TCP",
        "port": 456
    }, "tcpSocket", {
        "port": 456
    }),
])
def test_network_health_check(health_check, expected_action_key, expected_action):
    app = {"id": "/server", "healthChecks": [health_check]}

    translated = app_translator.translate_app(app, EMPTY_SETTINGS)

    probe = translated.deployment['spec']['template']['spec']['containers'][0]['livenessProbe']
    assert probe[expected_action_key] == expected_action

    if not health_check['protocol'].startswith('MESOS'):
        assert any(["check that the K8s probe is using the correct port" in w\
                    for w in translated.warnings])


def test_port_from_port_definitions():
    app = {
        "id": "/server",
        "healthChecks": [{
            "protocol": "MESOS_TCP",
            "portIndex": 2
        }],
        "portDefinitions": [{
            "port": 443
        }, {
            "port": 123
        }, {
            "port": 456
        }]
    }

    translated = app_translator.translate_app(app, EMPTY_SETTINGS)

    probe = translated.deployment['spec']['template']['spec']['containers'][0]['livenessProbe']
    assert probe['tcpSocket'] == {'port': 456}


def test_port_from_port_mappings():
    app = {
        "id": "/server",
        "healthChecks": [{
            "protocol": "MESOS_TCP",
            "portIndex": 1
        }],
        "container": {
            "portMappings": [{
                "hostPort": 119,
                "containerPort": 80
            }, {
                "hostPort": 332,
                "containerPort": 443
            }]
        }
    }

    translated = app_translator.translate_app(app, EMPTY_SETTINGS)

    probe = translated.deployment['spec']['template']['spec']['containers'][0]['livenessProbe']
    assert probe['tcpSocket'] == {'port': 443}


def test_port_zero_in_health_check():
    # TODO (asekretenko): This test should be adjusted when we introduce
    # a uniform support for port 0 throughout the app translation.
    app = {
        "id": "/server",
        "healthChecks": [{
            "protocol": "MESOS_TCP",
            "portIndex": 1
        }],
        "container": {
            "portMappings": [{
                "hostPort": 119,
                "containerPort": 80
            }, {
                "hostPort": 332,
                "containerPort": 0
            }]
        }
    }

    translated = app_translator.translate_app(app, EMPTY_SETTINGS)

    assert any(['using port 0' in w for w in translated.warnings])
