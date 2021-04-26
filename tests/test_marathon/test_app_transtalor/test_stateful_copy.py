import yaml
import json
from dcos_migrate.plugins.marathon import app_translator, stateful_copy

from .common import DummyAppSecretMapping

probes_app_definition = {
    "id": "/stateful-healthy",
    "healthChecks": [{
        "protocol": "COMMAND",
        "command": {
            "value": "exit 0"
        }
    }],
    "version": "2021-01-01Z00:00:00",
    "container": {
        "volumes": [{
            "containerPath": "/var/lib/test-data",
            "hostPath": "test-data",
            "mode": "RW"
        }, {
            "containerPath": "test-data",
            "mode": "RW",
            "persistent": {
                "type": "root",
                "size": 128,
                "constraints": []
            }
        }]
    }
}


def new_settings(image: str = "busybox"):
    return app_translator.Settings(
        app_translator.ContainerDefaults(
            image=image,
            working_dir=".",
        ),
        app_secret_mapping=DummyAppSecretMapping(),
    )


def test_artifact_output():
    k8s_probe_statefulset = app_translator.translate_app(probes_app_definition, new_settings()).deployment
    artifacts = stateful_copy.stateful_migrate_artifacts(probes_app_definition, k8s_probe_statefulset)

    config_lines = artifacts["config.sh"].split("\n")
    assert ('APP_ID="/stateful-healthy"' in config_lines)
    assert ('MOUNT_NAMES=("test-data")' in config_lines)
    assert ('K8S_APP_ID="stateful-healthy"' in config_lines)

    sleeper_patch = yaml.safe_load(artifacts["k8s-sleeper-command-patch.yaml"])
    assert sleeper_patch['spec']['template']['spec']['containers'][0]["livenessProbe"] == None

    original_patch = yaml.safe_load(artifacts["k8s-original-command-patch.yaml"])
    assert original_patch['spec']['template']['spec']['containers'][0]["livenessProbe"]['exec']['command'] == [
        '/bin/sh', '-c', 'exit 0'
    ]

    app_sleeper_patch = json.loads(artifacts["dcos-sleeper-command-patch.json"])
    assert app_sleeper_patch == {'command': 'sleep 604800', 'checks': [], 'healthChecks': []}
