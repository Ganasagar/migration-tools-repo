#!/usr/bin/env python3

# To run doc tests, use `pytest --doctest-modules`

#pylint: disable=missing-docstring,fixme

import argparse
import logging
import sys
import dcos_migrate.utils as utils

# This script relies on python-yaml installed via pip, system package manager or some other means.
from typing import Any

import yaml

from dcos_migrate.plugins.marathon.app_secrets import TrackingAppSecretMapping, SecretReference
from dcos_migrate.plugins.marathon.app_translator import ContainerDefaults, Settings, load, translate_app, marathon_app_id_to_k8s_app_id
from dcos_migrate.plugins.marathon.service_translator import translate_service
from dcos_migrate.plugins.marathon import app_secrets

log = logging.getLogger(__name__)  #pylint: disable=invalid-name


class FakeAppSecretMapping(app_secrets.AppSecretMapping):
    def get_reference(self, app_secret_name: str) -> SecretReference:
        return SecretReference(app_secret_name, app_secret_name)

    def get_image_pull_secret_name(self, app_secret_name: str) -> str:
        return app_secret_name


def translate(path: str, settings: Settings, selected_app_id: str) -> None:
    apps = load(path)
    for app in apps:
        app_id = app.get('id', "(NO ID)")
        if selected_app_id and selected_app_id != app_id:
            continue
        app_label = marathon_app_id_to_k8s_app_id(app_id)
        dcos_package_name = app.get('labels', {}).get("DCOS_PACKAGE_NAME")

        if dcos_package_name is None:
            translated = translate_app(app, settings)
            print("# Converted from an app {}".format(app_id))
            print("\n\n".join([''] + translated.warnings).replace('\n', '\n# '))
            print(yaml.safe_dump(translated.deployment))
            print("---")

            k8s_app_id: str = translated.deployment['metadata']['labels']['app']
            result, warnings = translate_service(k8s_app_id, app)
            if result:
                print("# Converted from an app {}".format(app_id))
                print("\n\n".join([''] + list(warnings)).replace('\n', '\n# '))
                print(yaml.safe_dump(result))
        else:
            print('# Skipped an app {}: it is installed from a DCOS package "{}"'.format(app_id, dcos_package_name))

        print('---')


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)5s %(message)s')

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-commands available')

    translate_cmd = subparsers.add_parser("translate",
                                          help='Translate the Marathon app into a K8s deployment',
                                          parents=[])
    translate_cmd.add_argument("--app-id", type=str, help="Translate only app with this ID")

    translate_cmd.add_argument("--path", type=str, help="File with app definitions")
    translate_cmd.add_argument("--default-image",
                               type=str,
                               help="Default image for apps that were running without an image")

    translate_cmd.add_argument(
        "--container-working-dir",
        type=str,
        help="workingDir of the main container on K8s."
        " Files from Marathon app's `fetch` will be downloaded there by a generated init container.")

    def translate_func(args: Any) -> None:
        secret_mapping = FakeAppSecretMapping()
        settings = Settings(container_defaults=ContainerDefaults(
            image=args.default_image,
            working_dir=args.container_working_dir,
        ),
                            app_secret_mapping=secret_mapping)

        return translate(args.path, settings, args.app_id)

    translate_cmd.set_defaults(func=translate_func)

    if len(sys.argv) < 2:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
