import json
import logging
import re
import os.path

from collections import namedtuple

Settings = namedtuple('Settings', ['container_defaults', 'imported_k8s_secret_name'])

ContainerDefaults = namedtuple('ContainerDefaults', ['image', 'working_dir'])

log = logging.getLogger(__name__) #pylint: disable=invalid-name

class Translated(object):
    """
        A return value of all translator functions in GROUP_MAPPINGS
    """
    def __init__(self, update=None, warnings=None):
        self.update = {} if update is None else update
        self.warnings = [] if warnings is None else warnings

    def merged_with(self, other):
        return Translated(
            update=deep_merge(self.update, other.update),
            warnings=self.warnings + other.warnings
        )


def apply_mapping(mapping: dict, data: dict, error_location: str):
    """
    >>> mapper = lambda n: Translated({"outer": [{"inner": n*2}]})
    >>> result, _ = apply_mapping({"foo": mapper}, {"foo": 21}, "")
    >>> result == {"outer": [{"inner": 42}]}
    True

    >>> mapper = lambda d: Translated({"product": d['foo'] * d['bar']})
    >>> result, _ = apply_mapping({("foo", "bar"): mapper}, {"foo": 21, "bar": 2}, "")
    >>> result == {"product": 42}
    True

    >>> mapper = lambda n: Translated({"result": n})
    >>> apply_mapping({"foo": mapper}, {"foo": 1, "bar": 2, "baz": 0}, "app")
    Traceback (most recent call last):
        ...
    RuntimeError: "app" has fields "bar", "baz" that are not present in the field mappings

    >>> mapper = lambda n: Translated({"result": n})
    >>> apply_mapping({"foo": mapper, "bar": mapper}, {"foo": 1, "bar": 2}, "app")
    Traceback (most recent call last):
        ...
    Exception: Error composing the result object for "app": Conflicting values for .result: 2 and 1

    >>> broken_mapper = lambda n: str(n)
    >>> apply_mapping({"foo": broken_mapper}, {"foo": 1}, "app")
    Traceback (most recent call last):
        ...
    Exception: Bad translation result in "app" for key "foo"

    """
    def map_group(group, mapper):
        if isinstance(group, tuple):
            fields = set(group) & data.keys()
            return fields, mapper({field: data[field] for field in fields})

        try:
            value = data[group]
        except KeyError:
            return set(), Translated()

        return {group}, mapper(value)

    unknown = data.keys()
    result = {}
    warnings = []

    for key in sorted(mapping.keys(), key = str):
        mapper = mapping[key]
        mapped_app_fields, translated = map_group(key, mapper)
        if not isinstance(translated, Translated):
            raise Exception('Bad translation result in "{}" for key "{}"'.format(error_location, key))

        warnings += ['"{}": {}'.format(key, warn) for warn in translated.warnings]

        try:
            result = deep_merge(result, translated.update)
        except UpdateConflict as err:
            raise Exception(
                'Error composing the result object for "{}": {}'.format(error_location, err))

        unknown -= mapped_app_fields

    if unknown:
        # We intentionally crash the script when unknown fields are discovered.
        # The fields that cannot or should not be mapped should be explicitly added
        # into the corresponding `generate_..._mappings()` function.
        raise RuntimeError(
            '"{}" has fields {} that are not present in the field mappings'.format(
                error_location, ', '.join('"{}"'.format(_) for _ in sorted(unknown))))

    return result, warnings



def pod_spec_update(fields):
    return {'spec': {'template': {'spec': fields}}}


def main_container(fields):
    # NOTE: All updates for the main container set the same "name" field.
    assert 'name' not in fields
    _fields = {'name': 'main'}
    _fields.update(fields)

    return pod_spec_update({'containers': [_fields]})


def translate_container_command(fields):
    # Marathon either supports args (with a container specified), or cmd. Not both.
    # Marathon does not have a way to override the entrypoint for a container.
    # https://github.com/mesosphere/marathon/blob/b5023142bdf8bd75f187df897ab4d70f4fe03b24/src/test/scala/mesosphere/marathon/api/v2/json/AppDefinitionTest.scala#L131-L132
    if 'cmd' in fields:
        cmdline = ["/bin/sh", "-c", fields['cmd']]

        # FIXME: Sanitize the cmdline against DCOS-specific stuff!
        return Translated(update=main_container({'command': cmdline}))
    elif 'args' in fields:
        # FIXME: Sanitize the cmdline against DCOS-specific stuff!
        return Translated(update=main_container({'args': fields['args']}))
    else:
        return Translated()

RESOURCE_TRANSLATION = {
    'cpus': lambda cpus: ('cpu', cpus),
    'mem': lambda mem: ('memory', '{}Mi'.format(mem)),
    'disk': lambda disk: ('ephemeral-storage', '{}Mi'.format(disk)),
    'gpus': lambda gpus: ('nvidia.com/gpu', '{}'.format(gpus)),
}


def translate_resources(fields):
    app_requests = fields.copy()
    app_limits = app_requests.pop('resourceLimits', {})

    def iter_requests():
        for key, value in app_requests.items():
            if value != 0 :
                yield RESOURCE_TRANSLATION[key](value)

    def iter_limits():
        for key in app_requests.keys() | app_limits.keys():
            if key in app_limits:
                limit = app_limits[key]
                if limit != "unlimited":
                    yield RESOURCE_TRANSLATION[key](limit)
            else:
                limit_from_requests = app_requests[key]
                if limit_from_requests != 0:
                    yield RESOURCE_TRANSLATION[key](limit_from_requests)

    resources = {'requests': dict(iter_requests()), 'limits': dict(iter_limits())}
    update = main_container({'resources': {k: v for k, v in resources.items() if v}})
    return Translated(update)


class MissingSecretSource(Exception):
    pass

class AdditionalFlagNeeded(Exception):
    """
    Used to indicate that for migrating this specific app the user is obliged
    to specify a flag which could otherwise have been omitted.
    """
    pass


# FIXME: import this from the secretrs migration code!
def clean_secret_key(key: str) -> str:
    _invalid_secret_key = re.compile('[^-._a-zA-Z0-9]')
    # Replace DC/OS folders with dots
    key = key.replace('/', '.')
    # Replace other invalid characters with `_`
    # `folder/sec!ret` becomes `folder.sec_ret`
    return _invalid_secret_key.sub('_', key)


def translate_env(fields, imported_k8s_secret_name, error_location):
    secrets = fields.get('secrets', {})

    def translate_secret(secret):
        try:
            key = secrets[secret]['source']
        except KeyError:
            raise MissingSecretSource(
                '{} is broken: source for an env secret "{}" not specified'.format(
                    error_location, secret))

        if not imported_k8s_secret_name:
            raise AdditionalFlagNeeded(
                '{} app is using secrets; please specify the'
                ' `--imported-k8s-secret-name` and run again'.format(error_location))

        return {
            'secretKeyRef': {'name': imported_k8s_secret_name, 'key': clean_secret_key(key)}
        }


    translated = []
    not_translated = {}

    # FIXME: Sanitize against DCOS-specific stuff.
    for var, value in fields.get('env', {}).items():
        if isinstance(value, dict):
            if value.keys() != {'secret'}:
                not_translated[var] = value
            else:
                translated.append({"name": var, "valueFrom": translate_secret(value['secret'])})
        else:
            translated.append({"name": var, "value": value})

    return Translated(
        update=main_container({'env': translated}),
        warnings=["could not translate the following variables:\n" + json.dumps(not_translated)]\
            if not_translated else [],
    )


def translate_multitenancy(fields):
    # FIXME: Translate groups and roles.

    # TODO(asekretenko): Consider adding prefix or another label to show that
    # this has been generated by the DCOS migration script.


    app_id = fields['id'].lstrip('/').replace('/', '.')
    selector_labels = {'app': app_id}
    return Translated(update={
        'metadata': {'name': app_id, 'labels': {'app': app_id}},
        'spec': {
            'selector': {'matchLabels': selector_labels},
            'template': {'metadata': {'labels': selector_labels}}}
    })


class InvalidAppDefinition(Exception):
    pass


def get_network_probe_builder(get_port_by_index):
    def build_network_probe(fields):
        protocol = fields.pop('protocol')
        port = fields.pop('port', None)
        index = fields.pop('portIndex', 0)
        path = fields.pop('path', '/')

        warnings = [] if not fields else \
            ['Non-translatable health check fields: {}'.format(try_oneline_dump(fields))]

        use_host_port = protocol in ['TCP', 'HTTP', 'HTTPS']
        port = get_port_by_index(index, use_host_port) if port is None else port

        # TODO (asekretenko): The app translator should choose a value for each port==0
        # once, and ensure that the same value is used for the same port
        # by different parts of the generated manifest.
        if port == 0:
            warnings.append(
                "The app is using port 0 (auto-assigned by Marathon) in a health check."
                " Please make sure that the generated K8s probe is using a correct port number.")

        if protocol in ['MESOS_TCP', 'TCP']:
            return Translated({'tcpSocket': {'port': port}}, warnings)

        if protocol in ['MESOS_HTTP', 'HTTP', 'MESOS_HTTPS', 'HTTPS']:
            scheme = 'HTTPS' if protocol in ['MESOS_HTTPS', 'HTTPS'] else 'HTTP'
            return Translated({'httpGet': {'port': port, 'scheme': scheme, 'path': path}}, warnings)

        raise InvalidAppDefinition("Invalid `protocol` in a health check: {}".format(protocol))

    return build_network_probe


def rename(name):
    return lambda _: Translated({name: _})


def health_check_to_probe(check, get_port_by_index, error_location):
    flattened_check = flatten(check)

    mapping = {
        'gracePeriodSeconds': rename('initialDelaySeconds'),
        'intervalSeconds': rename('periodSeconds'),
        'maxConsecutiveFailures': rename('failureThreshold'),
        'timeoutSeconds': rename('timeoutSeconds'),
        'delaySeconds': skip_if_equals(15),
        'ipProtocol': skip_if_equals("IPv4"),
        'ignoreHttp1xx': skip_if_equals(False),
        'protocol': skip_quietly,
    }

    if check['protocol'] == 'COMMAND':
        mapping['command.value'] = lambda command: Translated({'command': ["/bin/sh", "-c", command]})
    else:
        mapping[('protocol', 'port', 'portIndex', 'path')] = get_network_probe_builder(get_port_by_index)

    probe, warnings = apply_mapping(mapping, flattened_check, error_location)
    probe.setdefault('initialDelaySeconds', 300)
    probe.setdefault('periodSeconds', 60)
    probe.setdefault('timeoutSeconds', 20)

    if check['protocol'] in ['TCP', 'HTTP', 'HTTPS']:
        warnings.append(
            "The app is using a deprecated Marathon-level health check:\n" +
            try_oneline_dump(check) +
            "\nPlease check that the K8s probe is using the correct port.")

    return probe, warnings


def translate_health_checks(fields, error_location):
    def get_port_by_index(index, use_host_port=False):
        port_mappings = fields.get('container', {}).get('portMappings')
        port_definitions = fields.get('portDefinitions')
        if port_mappings is None == port_definitions is None:
            raise InvalidAppDefinition("Cannot get port by index as both portDefinitions and container.portMappings are set")

        if port_definitions is not None:
            try:
                port_data = port_definitions[index]
            except IndexError:
                raise InvalidAppDefinition("Port index {} used in health check missing from `portDefinitions`".format(index))

            try:
                return port_data['port']
            except KeyError:
                raise InvalidAppDefinition("`portDefinitions` contain no 'port' at index {} used in health check".format(index))

        try:
            port_data = port_mappings[index]
        except IndexError:
            raise InvalidAppDefinition("Port index {} used in health check missing from `container.portMappings`".format(port_index))

        key = 'hostPort' if use_host_port else 'containerPort'
        try:
            return port_data[key]
        except KeyError:
            raise InvalidAppDefinition("`container.portMappings` contain no '{}' at index {} used in health check".format(key, index))

    health_checks = fields.get('healthChecks', [])
    if len(health_checks) < 1:
        return Translated()

    livenessProbe, warnings = health_check_to_probe(health_checks[0], get_port_by_index, error_location)

    excess_health_checks = health_checks[1:]
    if excess_health_checks:
        warnings.append(
            'Only the first app health check is converted into a liveness probe.\n'
            'Dropped health checks:\n{}'.format(
                try_oneline_dump(excess_health_checks)))

    return Translated(
        update=main_container({'livenessProbe': livenessProbe}),
        warnings=warnings
    )


def skip_quietly(_):
    return Translated()


def not_translatable(_):
    return Translated(warnings=["field not translatable"])


def try_oneline_dump(obj):
    dump = json.dumps(obj)
    return dump if len(dump) <= 78 else json.dumps(obj, indent=2)


def skip_if_equals(default):
    if not default:
        return lambda value: Translated(warnings=[] if not value else [
            'Cannot translate non-empty value\n{}'.format(try_oneline_dump(value))])

    return lambda value: Translated(warnings=[] if value == default else [
        'A value\n{}\ndifferent from the default\n{}\ncannot be translated.'.format(
            try_oneline_dump(value),
            try_oneline_dump(default)
        )])


def generate_root_mapping(settings: Settings, error_location):

    return {
        ('args', 'cmd'): translate_container_command,

        ('backoffFactor', 'backoffSeconds'): skip_if_equals({'backoffFactor':1.0, 'backoffSeconds': 1.0}),

        'constraints': skip_if_equals([]),

        ('container', 'fetch'):
            get_container_translator(settings.container_defaults, error_location),

        ('cpus', 'mem', 'disk', 'gpus', 'resourceLimits'): translate_resources,

        'dependencies': skip_if_equals([]),

        'deployments': skip_quietly,

        ('env', 'secrets'):
            lambda fields: translate_env(fields, settings.imported_k8s_secret_name, error_location),

        'executor': skip_if_equals(""),

        ('healthChecks', 'container', 'portDefinitions'):
            lambda fields: translate_health_checks(fields, error_location),

        ('acceptedResourceRoles', 'id', 'role'): translate_multitenancy,

        'instances': lambda n: Translated(update={'spec': {'replicas': n}}),

        'killSelection': skip_if_equals("YOUNGEST_FIRST"),

        'labels': skip_if_equals({}),  # translate_labels,

        'maxLaunchDelaySeconds': skip_if_equals(300),

        ('networks', 'portDefinitions', 'requirePorts'): skip_if_equals({}),  # translate_networking,

        'residency': skip_if_equals({}),

        'taskKillGracePeriodSeconds': not_translatable,

        'tasksHealthy': skip_quietly,
        'tasksRunning': skip_quietly,
        'tasksStaged': skip_quietly,
        'tasksUnhealthy': skip_quietly,

        'unreachableStrategy': not_translatable,

        'upgradeStrategy': not_translatable,

        'user': skip_if_equals("nobody"),

        'version': skip_quietly,
        'versionInfo': skip_quietly,
    }


EXTRACT_COMMAND = dict(
    [('.zip', 'gunzip')] +\
    [(ext, 'tar -xf') for ext in ['.tgz', '.tar.gz', '.tbz2', '.tar.bz2', '.txz', '.tar.xz']]
)


def generate_fetch_command(uri: str, allow_extract: bool, executable: bool):
    _, _, filename = uri.rpartition('/') # NOTE: The path separator is always '/', even on Windows.
    _, ext = os.path.splitext(filename)

    postprocess = 'chmod a+x' if executable else \
        (EXTRACT_COMMAND.get(ext, '') if allow_extract else '')

    fmt = '( wget -O "{fn}" "{uri}" && {postprocess} "{fn}" )' if postprocess else\
          '( wget -O "{fn}" "{uri}")'

    return fmt.format(fn=filename, uri=uri, postprocess=postprocess)


def translate_fetch(fetches, artifacts_volume_name):
    warnings = []

    def iter_command():
        yield 'set -x'
        yield 'set -e'
        yield 'FETCH_PID_ARRAY=()'

        for fetch in fetches:
            fetch = fetch.copy()
            uri = fetch.pop('uri')
            cache = fetch.pop('cache', False)
            extract = fetch.pop('extract', True)
            executable = fetch.pop('executable', False)
            if fetch:
                warnings.append('Unknown fields in "fetch": {}', json.dumps(fetch))

            if cache:
                warnings.append(
                    '`cache=true` requested for fetching "{}" has been ignored'.format(uri))

            if uri.startswith('file://'):
                warnings.append('Fetching a local file {} is not portable'.format(uri))

            yield generate_fetch_command(uri, extract, executable) + ' & FETCH_PID_ARRAY+=("$!")'

        yield 'for pid in ${FETCH_PID_ARRAY[@]}; do wait $pid || exit $?; done'

    return Translated(
        update=pod_spec_update({
            "initContainers": [{
                "name": "fetch",
                "image": "bash:5.0",
                "command": ['bash', '-c', '\n'.join(iter_command())],
                "volumeMounts": [{
                    "name": artifacts_volume_name,
                    "mountPath": "/fetch_artifacts"
                }],
                "workingDir": "/fetch_artifacts",
            }],
            "volumes": [{"name": artifacts_volume_name, "emptyDir": {}}]
        }),
        warnings=warnings,
    )


def get_container_translator(defaults: ContainerDefaults, error_location):
    def translate_container(fields):
        container, warnings = apply_mapping(
            mapping={
                "docker.forcePullImage": lambda _: Translated({'imagePullPolicy': "Always" if _ else "IfNotPresent"}),
                "docker.image": lambda _: Translated({'image': _}),
                "docker.parameters": skip_if_equals([]),
                "docker.privileged": skip_if_equals(False),
                "docker.pullConfig.secret": skip_if_equals({}),
                "linuxInfo": skip_if_equals({}),
                "portMappings": skip_if_equals({}),
                "volumes": skip_if_equals([]),
                "type": skip_quietly,
            },
            data=flatten(fields.get('container', {})),
            error_location=error_location + ", container"
        )

        if 'image' not in container:
            if defaults.image:
                container['image'] = defaults.image
            else:
                raise AdditionalFlagNeeded(
                    '{} has no image; please specify non-empty `--default-image` and run again'.format(error_location)
                )

            if defaults.working_dir:
                container['workingDir'] = defaults.working_dir

        fetch = Translated()
        if fields.get('fetch'):
            if not defaults.working_dir:
                raise AdditionalFlagNeeded(
                    '{} is using "fetch"; please specify non-empty `--container-working-dir` and run again'.format(error_location)
                )

            warnings.append('This app uses "fetch"; consider using a container image instead.')

            # NOTE: volumeMounts might already be non-empty after translating "volumes"
            container.setdefault("volumeMounts", []).append({
                "name": 'fetch-artifacts',
                "mountPath": defaults.working_dir
            })

            fetch = translate_fetch(fields['fetch'], 'fetch-artifacts')

        return Translated(update=main_container(container), warnings=warnings).merged_with(fetch)

    return translate_container


def flatten(dictionary):
    """
    >>> flatten({'foo':{'bar':{'baz': 0}, 'deadbeef': 1}, '42': 3})
    {'foo.bar.baz': 0, 'foo.deadbeef': 1, '42': 3}
    """
    def iterate(data, prefix):
        for key, value in data.items():
            prefixed_key = prefix + key
            if isinstance(value, dict):
                for prefixed_subkey, val in iterate(value, prefixed_key + '.'):
                    yield prefixed_subkey, val
            else:
                yield prefixed_key, value

    return dict(iterate(dictionary, ""))


class InvalidInput(Exception):
    pass

def load(path: str):
    with open(path) as input_file:
        apps = json.load(input_file)

    if isinstance(apps, list):
        return apps

    if not isinstance(apps, dict):
        raise InvalidInput(
            "The top level of {} is neither a dict nor a list".format(path))

    if 'apps' in apps:
        return apps['apps']

    log.warning("Interpreting %s as containing a single app", path)
    return [apps]


class UpdateConflict(Exception):
    pass


def deep_merge(first, second, debug_prefix=''):
    """
    >>> result = deep_merge({5: 6, 3: {"bar": "baz"}}, {1: 2, 3: {"foo": "bar"}})
    >>> result == {1: 2, 3: {"foo": "bar", "bar": "baz"}, 5: 6}
    True

    >>> result = deep_merge({1: 2, 3: {"foo": "bar"}}, {5: 6, 3: {"bar": "baz"}})
    >>> result == {1: 2, 3: {"foo": "bar", "bar": "baz"}, 5: 6}
    True

    >>> result = deep_merge({3: [{"foo": "bar"}]}, {3: [{"bar": "baz"}, "deadbeef"]})
    >>> result == {3: [{"foo": "bar", "bar": "baz"}, "deadbeef"]}
    True

    >>> result = deep_merge({3: [{"bar": "baz"}, "deadbeef"]}, {3: [{"foo": "bar"}]})
    >>> result == {3: [{"foo": "bar", "bar": "baz"}, "deadbeef"]}
    True

    >>> deep_merge({"foo": 1}, {"foo": 1}) == {"foo": 1}
    True

    >>> deep_merge({"foo": 1}, {"foo": 2}) # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UpdateConflict: Conflicting values for .foo: 1 and 2
    """
    if all(isinstance(_, dict) for _ in (first, second)):
        def iter_items():
            for key in first.keys() - second.keys():
                yield key, first[key]
            for key in second.keys() - first.keys():
                yield key, second[key]
            for key in first.keys() & second.keys():
                yield key, deep_merge(first[key], second[key], debug_prefix + '.' + str(key))

        return dict(iter_items())

    if all(isinstance(_, list) for _ in (first, second)):
        min_len = min(len(first), len(second))
        return [deep_merge(first[n], second[n], '{}[{}]'.format(debug_prefix, n)) for n in range(min_len)] \
            + first[min_len:] + second[min_len:]

    if first == second:
        return first

    raise UpdateConflict(
        'Conflicting values for {}: {} and {}'.format(debug_prefix, first, second))


def translate_app(app: dict, container_defaults: ContainerDefaults):
    error_location = "app " + app.get('id', '(NO ID)')

    mapping = generate_root_mapping(container_defaults, error_location)

    try:
        definition, warnings = apply_mapping(mapping, app, error_location)
    except InvalidAppDefinition as err:
        raise InvalidAppDefinition('{} at {}'.format(err, error_location))

    definition.update({'apiVersion': 'apps/v1', 'kind': 'Deployment'})
    return definition, warnings
