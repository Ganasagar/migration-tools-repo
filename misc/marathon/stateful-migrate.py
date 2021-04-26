import argparse
import json
import logging
import subprocess
import sys
from typing import List, Dict, Any

from dcos_migrate.plugins.marathon import app_translator
from dcos_migrate.plugins.marathon.app_translator import Settings, ContainerDefaults
import migrate
from dcos_migrate.plugins.marathon.stateful_copy import configure_stateful_migrate


class ConfigureArgs:
    app_id: str


def run_escalating_failure(args: List[str]) -> str:
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0:
        print("\n\n\nCommand {} returned non-zero exit code {}!".format(args, result.returncode))
        print("\n\n\nstdout was this:")
        print(result.stdout.decode())
        print("\n\n\nstderr was this:")
        print(result.stderr.decode())
        sys.exit(1)
    else:
        return result.stdout.decode()


def get_dcos_app(marathon_app_id: str) -> Dict[str, Any]:
    """
    Get the app from DC/OS; return a tuple containing the app itself,

    :param marathon_app_id:
    :return:
    """
    text_result = run_escalating_failure(["dcos", "marathon", "app", "show", marathon_app_id])
    app = json.loads(text_result)
    del app["tasksRunning"]
    del app["tasks"]

    return app


def configure(conf: ConfigureArgs, translate_settings: Settings) -> None:
    # pull the marathon app
    original_marathon_app = get_dcos_app(conf.app_id)
    k8s_translate_result = app_translator.translate_app(original_marathon_app, translate_settings)
    configure_stateful_migrate(original_marathon_app, k8s_translate_result.deployment)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)5s %(message)s')

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-commands available', dest='cmd')
    configure_cmd = subparsers.add_parser(
        "configure",
        help='Generate configuration to push Marathon state to the kubernetes  the Marathon app into a K8s deployment',
        parents=[])
    configure_cmd.add_argument("app_id", type=str, help="Name of the app to target")
    configure_cmd.add_argument("--default-image",
                               type=str,
                               help="Default image for apps that were running without an image")
    configure_cmd.add_argument(
        "--container-working-dir",
        type=str,
        help="workingDir of the main container on K8s."
        " Files from Marathon app's `fetch` will be downloaded there by a generated init container.")

    def configure_func(args: Any) -> None:
        secret_mapping = migrate.FakeAppSecretMapping()
        settings = Settings(container_defaults=ContainerDefaults(
            image=args.default_image,
            working_dir=args.container_working_dir,
        ),
                            app_secret_mapping=secret_mapping)

        return configure(args, settings)

    configure_cmd.set_defaults(func=configure_func)

    if len(sys.argv) < 2:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
