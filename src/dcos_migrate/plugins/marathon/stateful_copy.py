import json
import shutil
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, NamedTuple

from dcos_migrate.plugins.marathon import app_translator
from dcos_migrate.plugins.marathon import volumes

STATE_PATH: Path = Path("dcos-migrate") / "migrate/marathon/stateful-copy"


def make_original_k8s_patch(original_service: Dict[str, Any]) -> Dict[str, Any]:
    containers_patch = [{
        "command": (c["command"] if "command" in c else None),
        "startupProbe": (c["startupProbe"] if "startupProbe" in c else None),
        "livenessProbe": (c["livenessProbe"] if "livenessProbe" in c else None),
        "readinessProbe": (c["readinessProbe"] if "readinessProbe" in c else None),
        "name": c["name"]
    } for c in original_service['spec']['template']['spec']['containers']]
    return {"spec": {"template": {"spec": {"containers": containers_patch}}}}


def make_sleeper_k8s_patch(original_service: Dict[str, Any]) -> Dict[str, Any]:
    containers_patch = [{
        "command": ["sleep", "604800"],
        "name": c["name"],
        "livenessProbe": None,
        "readinessProbe": None,
        "startupProbe": None
    } for c in original_service['spec']['template']['spec']['containers']]
    return {"spec": {"template": {"spec": {"containers": containers_patch}}}}


def make_sleeper_stateful_set(original_service: Dict[str, Any]) -> Dict[str, Any]:
    service: Dict[str, Any] = json.loads(json.dumps(original_service))
    patch = make_sleeper_k8s_patch(service)
    containers = patch['spec']['template']['spec']['containers']
    for i, c in enumerate(service['spec']['template']['spec']['containers']):
        c.update(containers[i])

    return service


def make_sleeper_app_patch() -> Dict[str, Any]:
    return {"command": "sleep 604800", "checks": [], "healthChecks": []}


class MountVolume(NamedTuple):
    name: str  # "containerPath" field of the persistent volume, the name as mounted in the Mesos sandbox
    path: str  # the path mounted in the container


def get_mount_vols(marathon_app: Dict[str, Any]) -> List[MountVolume]:
    vs = volumes.get_volumes(marathon_app)
    persistent_volume_names = set([v["containerPath"] for v in vs if "persistent" in v])

    return [
        MountVolume(name=v["hostPath"], path=v["containerPath"]) for v in vs
        if v.get("hostPath") in persistent_volume_names
    ]


def __bash_escape(s: str) -> str:
    """Rudimentary escape function"""
    return '"{}"'.format(s.replace('"', '\\"'))


def __as_bash_array(arr: List[str]) -> str:
    return " ".join([__bash_escape(v) for v in arr])


def copy_assets(output_dir: Path) -> None:
    shutil.copy("src/dcos_migrate/plugins/marathon/assets/instance/Makefile", output_dir / "Makefile")
    shutil.copy("src/dcos_migrate/plugins/marathon/assets/Makefile", STATE_PATH / "Makefile")
    shutil.copy("src/dcos_migrate/plugins/marathon/assets/README.md", STATE_PATH / "README.md")
    shutil.copytree("src/dcos_migrate/plugins/marathon/assets/bin", STATE_PATH / "bin", dirs_exist_ok=True)


def stateful_migrate_artifacts(original_marathon_app: Dict[str, Any],
                               k8s_translate_result: Dict[str, Any]) -> Dict[str, str]:
    # pull the marathon app
    app_id = original_marathon_app["id"]
    app_label = app_translator.marathon_app_id_to_k8s_app_id(app_id)

    output_dir = STATE_PATH / app_label
    output_dir.mkdir(exist_ok=True, parents=True)
    sleeper_dcos_json_path = "dcos-sleeper-command-patch.json"
    original_k8s_yaml_path = "k8s-original-command-patch.yaml"
    sleeper_k8s_yaml_path = "k8s-sleeper-command-patch.yaml"
    config_sh_path = "config.sh"

    # get the persistent volumes
    mount_vols = get_mount_vols(original_marathon_app)
    if len(mount_vols) == 0:
        raise Exception("Error, app {} is not a state app and has no persistent volumes".format(app_id))

    config = ""
    config += "APP_ID={}\n".format(__bash_escape(app_id))
    config += "K8S_APP_ID={}\n".format(__bash_escape(app_label))
    config += "MOUNT_NAMES=({})\n".format(__as_bash_array([v.name for v in mount_vols]))
    config += "MOUNT_PATHS=({})\n".format(__as_bash_array([v.path for v in mount_vols]))
    config += "DCOS_ORIGINAL_APP_VERSION={}\n".format(__bash_escape(original_marathon_app["version"]))

    sleeper_marathon_app = make_sleeper_app_patch()

    return {
        sleeper_dcos_json_path: json.dumps(sleeper_marathon_app, indent=2),
        original_k8s_yaml_path: yaml.dump(make_original_k8s_patch(k8s_translate_result)),
        sleeper_k8s_yaml_path: yaml.dump(make_sleeper_stateful_set(k8s_translate_result)),
        config_sh_path: config
    }


def configure_stateful_migrate(original_marathon_app: Dict[str, Any], k8s_translate_result: Dict[str, Any]) -> None:
    artifacts = stateful_migrate_artifacts(original_marathon_app, k8s_translate_result)
    # pull the marathon app
    app_id = original_marathon_app["id"]
    app_label = app_translator.marathon_app_id_to_k8s_app_id(app_id)

    output_dir = STATE_PATH / app_label
    output_dir.mkdir(exist_ok=True, parents=True)
    copy_assets(output_dir)

    for (filename, contents) in artifacts.items():
        (output_dir / filename).write_text(contents)
    print(
        "Stateful app {} needs to have its data copied. Please consult README.md in {} for instructions on how to proceed."
        .format(app_id, STATE_PATH))
