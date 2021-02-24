import argparse
import base64
import json
import os
import requests
import subprocess
import sys
import urllib
from typing import Dict, List, Union


class DCOSSecretsService:

    def __init__(self, url: str, token: str, verify: Union[bool, str]):
        self.url = url + '/secrets/v1'
        self.auth = 'token=' + token
        self.verify = verify
        self.store = 'default'

    def list(self, path: str = '') -> List[str]:
        r = requests.get(
            self.url + '/secret/{store}/{path}?list=true'.format(
                store=urllib.parse.quote(self.store), path=urllib.parse.quote(path)
            ),
            headers={'Authorization': self.auth},
            verify=self.verify,
        )
        r.raise_for_status()
        return r.json()['array']

    def get(self, path: str, key: str) -> Dict[str, str]:
        # There are two types of secrets: text and binary.  Using `Accept: */*`
        # the returned `Content-Type` will be `application/octet-stream` for
        # binary secrets and `application/json` for text secrets.
        #
        # Returns the secret as:
        # {
        #   "path": "...",
        #   "key": "...",
        #   "type": "{text|binary}",
        #   "value": "base64(value)"
        # }
        full_path = (path + '/' + key).strip('/')
        url = self.url + '/secret/{store}/{path}'.format(
            store=urllib.parse.quote(self.store), path=urllib.parse.quote(full_path)
        )
        r = requests.get(
            url,
            headers={'Authorization': self.auth, 'Accept': '*/*'},
            verify=self.verify,
        )
        r.raise_for_status()
        content_type = r.headers['Content-Type']
        if content_type == 'application/octet-stream':
            response = {
                'type': 'binary',
                'value': base64.b64encode(r.content).decode('ascii')
            }
        else:
            assert content_type == 'application/json', content_type
            response = r.json()
            response['type'] = 'text'
            # Always encode the secret as base64, even when it is safe UTF-8 text.
            # This obscures the values to prevent unintentional exposure.
            response['value'] = base64.b64encode(response['value'].encode('utf-8')).decode('ascii')
        # Always add the `path` and `key` values to the JSON response. Ensure the key always has a
        # value by taking the last component of the path if necessary.
        if not key:
            parts = path.rsplit('/', 1)
            key = parts.pop()
            parts.append('')
            path = parts[0]
        response['path'] = path
        response['key'] = key
        return response


def get_dcos_cluster_id(dcos_cli: str) -> str:
    p = subprocess.run(
        [dcos_cli, 'cluster', 'list', '--attached', '--json'],
        stdout=subprocess.PIPE,
        timeout=10 * 60,
        check=True,
    )
    j = json.loads(p.stdout.decode('utf-8'))
    return j[0]['cluster_id']


def get_dcos_token(dcos_cli: str) -> str:
    p = subprocess.run(
        [dcos_cli, 'config', 'show', 'core.dcos_acs_token'],
        stdout=subprocess.PIPE,
        timeout=10 * 60,
        check=True,
    )
    return p.stdout.decode('ascii').strip()


def get_dcos_url(dcos_cli: str) -> str:
    p = subprocess.run(
        [dcos_cli, 'config', 'show', 'core.dcos_url'],
        stdout=subprocess.PIPE,
        timeout=10 * 60,
        check=True,
    )
    return p.stdout.decode('ascii').strip().rstrip('/')


def run(argv: List[str]) -> None:
    parser = argparse.ArgumentParser(description='Backup secrets from DC/OS secrets service.')
    parser.add_argument(
        '--path', default='', help='DC/OS secrets namespace to export (default: all secrets)'
    )
    parser.add_argument(
        '--output', default=None, help='DC/OS secrets output file (default: stdout)'
    )
    parser.add_argument(
        '--dcos-cli', default=None, help='DC/OS CLI (default: dcos)'
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--no-verify', dest='verify', default=True, action='store_false',
        help='do not verify connections to DC/OS (insecure)'
    )
    group.add_argument(
        '--ca-file', dest='verify', help='specify a CA bundle file to verify connections to DC/OS'
    )

    args = parser.parse_args(argv)
    path = args.path
    dcos_cli = args.dcos_cli
    if dcos_cli is None:
        dcos_cli = os.getenv("DCOS_CLI", 'dcos')

    cluster_id = get_dcos_cluster_id(dcos_cli)
    url = get_dcos_url(dcos_cli)
    token = get_dcos_token(dcos_cli)

    s = DCOSSecretsService(url, token, args.verify)
    secrets = []
    keys = s.list(path)
    if keys:
        # Path is a folder containing secrets
        for key in s.list(path):
            secrets.append(s.get(path, key))
    else:
        # Expect path to name a specific secret
        secrets.append(s.get(path, ''))

    output = {
        'cluster_id': cluster_id,
        'secrets': secrets
    }
    if args.output is None:
        f = sys.stdout
    else:
        # To protect secrets open with read/write permissions only for owner
        f = os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT, 0o600), 'w')
    try:
        json.dump(output, f, indent=2, sort_keys=True)
    finally:
        if args.output is not None:
            f.close()


def main() -> None:
    run(sys.argv[1:])


if __name__ == '__main__':
    main()
