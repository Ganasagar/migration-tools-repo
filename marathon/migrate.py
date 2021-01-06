#!/usr/bin/env python3

# To run doc tests, use `pytest --doctest-modules`

#pylint: disable=missing-docstring,fixme

import argparse
import logging
import os.path
import re
import sys

# This script relies on python-yaml installed via pip, system package manager or some other means.
import yaml

from lib.app_translator import *

log = logging.getLogger(__name__) #pylint: disable=invalid-name

def translate(path: str, container_defaults: ContainerDefaults, selected_app_id):
    apps = load(path)
    for app in apps:
        app_id = app.get('id', "(NO ID)")
        if selected_app_id and selected_app_id != app_id:
            continue

        dcos_package_name = app.get('labels', {}).get("DCOS_PACKAGE_NAME")

        if dcos_package_name is None:
            result, warnings = translate_app(app, container_defaults)
            print("# Converted from an app {}".format(app_id))
            print("\n\n".join([''] + warnings).replace('\n', '\n# '))
            print(yaml.safe_dump(result))
        else:
            print('# Skipped an app {}: it is installed from a DCOS package "{}"'.format(app_id, dcos_package_name))

        print('---')


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)5s %(message)s')

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-commands available')

    translate_cmd = subparsers.add_parser(
        "translate", help='Translate the Marathon app into a K8s deployment', parents=[])
    translate_cmd.add_argument("--app-id", type=str, help="Translate only app with this ID")

    translate_cmd.add_argument(
        "--path", type=str, help="File with app definitions")
    translate_cmd.add_argument(
        "--default-image", type=str, help="Default image for apps that were running without an image")

    translate_cmd.add_argument(
        "--working-dir",
        type=str,
        help="workingDir of the main container on K8s."
             " Files from Marathon app's `fetch` will be downloaded there by a generated init container."
    )

    translate_cmd.add_argument(
        "--imported-k8s-secret-name",
        type=str,
        help="Name of the K8s secret into which the DCOS secrets have been imported"
    )

    def translate_func(args):
        settings = Settings(
            container_defaults=ContainerDefaults(
                image=args.default_image,
                working_dir=args.working_dir,
            ),
            imported_k8s_secret_name=args.imported_k8s_secret_name
        )

        return translate(args.path, settings, args.app_id)

    translate_cmd.set_defaults(func=translate_func)

    if len(sys.argv) < 2:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
