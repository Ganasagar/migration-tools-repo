import pytest

from dcos_migrate.plugins.marathon import app_translator
from dcos_migrate.plugins.marathon.app_secrets import TrackingAppSecretMapping

from .common import DummyAppSecretMapping
from typing import Sequence


def new_settings(image: str = "busybox"):
    return app_translator.Settings(
        app_translator.ContainerDefaults(
            image=image,
            working_dir=".",
        ),
        app_secret_mapping=DummyAppSecretMapping(),
    )


def test_happy_path_sleeper():
    settings = new_settings()
    hello_app = app_translator.load("tests/test_marathon/test_app_transtalor/resources/simple-command-app.json")[0]

    translated = app_translator.translate_app(hello_app, settings)

    assert (translated.deployment['kind'] == "Deployment")
    assert (translated.deployment['metadata']['name'] == "sleep")
    assert (translated.deployment['metadata']['labels'] == {'app': 'sleep'})
    assert (translated.deployment['spec']['replicas'] == 10)
    container = translated.deployment['spec']['template']['spec']['containers'][0]

    assert (container['command'] == ['/bin/sh', '-c', 'sleep 3600'])
    assert (container['image'] == 'busybox')
    assert (container['resources'] == {
        'requests': {
            'cpu': 0.01,
            'memory': '64Mi'
        },
        'limits': {
            'cpu': 0.01,
            'memory': '64Mi'
        }
    })

    assert (container['name'] == 'main')


@pytest.mark.parametrize('app_resource_fields,expected_k8s_resources', [
    ({}, {}),
    ({
        'cpus': 0.0
    }, {}),
    (
        {
            'cpus': 1
        },
        {
            'requests': {
                'cpu': 1
            },
            'limits': {
                'cpu': 1
            }
        },
    ),
    ({
        'cpus': 1,
        'resourceLimits': {
            'cpus': "unlimited"
        }
    }, {
        'requests': {
            'cpu': 1
        }
    }),
    ({
        'cpus': 1,
        'resourceLimits': {
            'cpus': 2
        }
    }, {
        'requests': {
            'cpu': 1
        },
        'limits': {
            'cpu': 2
        }
    }),
    ({
        'cpus': 0,
        'resourceLimits': {
            'cpus': 3
        }
    }, {
        'limits': {
            'cpu': 3
        }
    }),
    ({
        'resourceLimits': {
            'cpus': 4
        }
    }, {
        'limits': {
            'cpu': 4
        }
    }),
    ({
        'mem': 128,
        'resourceLimits': {
            'cpus': 4
        }
    }, {
        'requests': {
            'memory': '128Mi'
        },
        'limits': {
            'memory': '128Mi',
            'cpu': 4
        }
    }),
])
def test_resource_requests_and_limits(app_resource_fields, expected_k8s_resources):
    settings = new_settings()
    app = {"id": "app"}
    app.update(app_resource_fields)
    translated = app_translator.translate_app(app, settings)
    resources = translated.deployment['spec']['template']['spec']['containers'][0]['resources']
    assert resources == expected_k8s_resources


def test_image_in_app_makes_image_default_unnecessary():
    settings = new_settings()
    app = {"id": "app", "container": {"docker": {"image": "busybox"}}}
    translated = app_translator.translate_app(app, settings)
    assert translated.deployment['spec']['template']['spec']['containers'][0]['image'] == "busybox"


def test_image_should_be_present_somewhere():
    settings = new_settings(image=None)
    app = {"id": "app", "command": "sleep 300"}
    with pytest.raises(app_translator.AdditionalFlagNeeded, match=".*image.*"):
        app_translator.translate_app(app, settings)


def test_translates_args():
    settings = new_settings()
    hello_app = app_translator.load("tests/test_marathon/test_app_transtalor/resources/container-args-app.json")[0]

    translated = app_translator.translate_app(hello_app, settings)

    assert (translated.deployment['kind'] == "Deployment")
    assert (translated.deployment['metadata']['name'] == "args")
    container = translated.deployment['spec']['template']['spec']['containers'][0]

    assert (not "command" in container)
    assert (container['args'] == ["args", "passed", "to", "entrypoint"])


def test_env_secret():
    app = {
        "id": "foobarify",
        "env": {
            "FOO": {
                "secret": "bar"
            }
        },
        "secrets": {
            "bar": {
                "source": "/deadbeef/baz"
            }
        },
    }

    settings = app_translator.Settings(
        app_translator.ContainerDefaults(image="lazybox", working_dir=None),
        app_secret_mapping=TrackingAppSecretMapping(app['id'], app['secrets']),
    )

    translated = app_translator.translate_app(app, settings)
    env = translated.deployment['spec']['template']['spec']['containers'][0]['env']

    assert env == [{
        'name': 'FOO',
        'valueFrom': {
            'secretKeyRef': {
                'name': 'marathonsecret-foobarify',
                'key': 'deadbeef.baz',
            }
        }
    }]


def test_unreachable_strategy():
    settings = new_settings()
    app = {"id": "app", "unreachableStrategy": {"inactiveAfterSeconds": 123, "expungeAfterSeconds": 456}}
    translated = app_translator.translate_app(app, settings)
    tolerations = translated.deployment['spec']['template']['spec']['tolerations']

    # This test implicitly relies on the fact that "unreachableStartegy"
    # is the only thing that can result in tolerations being set.
    assert tolerations == [{
        'effect': 'NoExecute',
        'key': 'node.kubernetes.io/unreachable',
        'operator': 'Exists',
        'tolerationSeconds': 456
    }]

    assert any("inactiveAfterSeconds" in w and "123" in w for w in translated.warnings)


def test_upgrade_strategy():
    settings = new_settings()
    app = {"id": "app", "upgradeStrategy": {"minimumHealthCapacity": 0.6250, "maximumOverCapacity": 0.455}}
    translated = app_translator.translate_app(app, settings)

    assert translated.deployment['spec']['strategy'] == {
        "type": "RollingUpdate",
        "rollingUpdate": {
            "maxUnavailable": "37%",
            "maxSurge": "45%"
        }
    }


def test_task_kill_grace_period_seconds():
    settings = new_settings()
    app = {"id": "app", "taskKillGracePeriodSeconds": 123}
    translated = app_translator.translate_app(app, settings)
    assert translated.deployment['spec']['template']['spec']['terminationGracePeriodSeconds'] == 123


def __entries_list_to_dict(entries: Sequence[dict]) -> dict:
    result = {}
    for e in entries:
        result[e['name']] = e['value']

    return result


def test_translate_network_ports_env_vars():
    app = {
        "id": "nginx",
        "instances": 2,
        "container": {
            "type": "DOCKER",
            "docker": {
                "image": "nginx:1.14.2"
            },
            "portMappings": [{
                "name": "http",
                "hostPort": 0,
                "containerPort": 80,
                "labels": {
                    "VIP_0": "nginx:80"
                }
            }]
        }
    }
    settings = new_settings()
    translated = app_translator.translate_app(app, settings)
    container = translated.deployment['spec']['template']['spec']['containers'][0]

    resulting_env = __entries_list_to_dict(container['env'])
    assert (resulting_env == {'HOST': '0.0.0.0', 'PORTS': '80', 'PORT0': '80', 'PORT_HTTP': '80'})


def test_constraints():
    settings = new_settings()
    app = {
        "id":
        "/foo/barify",
        "constraints": [
            ["backpack", "UNIQUE"],
            ["hostname", "MAX_PER", 2],
            ["@hostname", "IS", "private-123.dcos-1.example.com"],
            ["@region", "LIKE", "antarctic"],
            ["@zone", "LIKE", "antarctic1024"],
            ["badluck", "GROUP_BY", 1],
            ["hostname", "UNIQUE"],
        ]
    }

    translated = app_translator.translate_app(app, settings)
    node_selector = translated.deployment['spec']['template']['spec']['nodeSelector']
    topology_spread = translated.deployment['spec']['template']['spec']['topologySpreadConstraints']
    affinity = translated.deployment['spec']['template']['spec']['affinity']

    assert node_selector == {
        "dcos.io/former-dcos-hostname": "private-123-dcos-1-example-com",
        "topology.kubernetes.io/region": "antarctic",
        "topology.kubernetes.io/zone": "antarctic1024",
    }

    labels = translated.deployment['spec']['template']['metadata']['labels']

    assert topology_spread == [
        {
            'labelSelector': {
                'matchLabels': labels
            },
            'maxSkew': 1,
            'topologyKey': 'backpack',
            'whenUnsatisfiable': 'DoNotSchedule'
        },
        {
            'labelSelector': {
                'matchLabels': labels
            },
            'maxSkew': 1,
            'topologyKey': 'kubernetes.io/hostname',
            'whenUnsatisfiable': 'DoNotSchedule'
        },
    ]

    assert any('GROUP_BY' in w for w in translated.warnings)

    assert translated.required_node_labels == {
        'backpack', 'kubernetes.io/hostname', 'dcos.io/former-dcos-hostname', 'topology.kubernetes.io/region',
        'topology.kubernetes.io/zone'
    }

    assert affinity == {
        'podAntiAffinity': {
            'requiredDuringSchedulingIgnoredDuringExecution': [{
                'labelSelector': {
                    'matchLabels': labels
                },
                'topologyKey': 'kubernetes.io/hostname',
            }],
        }
    }
