import json
import logging
import os.path

from .app_secrets import AppSecretMapping
from .common import (InvalidAppDefinition, AdditionalFlagNeeded, pod_spec_update, main_container, try_oneline_dump)
from .mapping_utils import (ListExtension, finalize_unmerged_list_extensions, MappingKey, Translated, apply_mapping)

from .constraints import translate_constraints
from .network_helpers import get_ports_from_app, effective_port, AppPort
from typing import (cast, Any, Callable, Dict, Iterator, List, Mapping, NamedTuple, Optional, Set, Sequence, Tuple,
                    Union)
import dcos_migrate.utils as utils
from . import volumes


class ContainerDefaults(NamedTuple):
    image: Optional[str]
    working_dir: Optional[str]


class Settings(NamedTuple):
    container_defaults: ContainerDefaults
    app_secret_mapping: AppSecretMapping


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


def translate_container_command(fields: Dict[str, Any]) -> Translated:
    # Marathon either supports args (with a container specified), or cmd. Not both.
    # Marathon does not have a way to override the entrypoint for a container.
    # https://github.com/mesosphere/marathon/blob/b5023142bdf8bd75f187df897ab4d70f4fe03b24/src/test/scala/mesosphere/marathon/api/v2/json/AppDefinitionTest.scala#L131-L132
    if 'cmd' in fields:
        cmdline = ["/bin/sh", "-c", fields['cmd']]

        # FIXME: Sanitize the cmdline against DCOS-specific stuff!
        return Translated(update=main_container({'command': cmdline}))

    if 'args' in fields:
        # FIXME: Sanitize the cmdline against DCOS-specific stuff!
        return Translated(update=main_container({'args': fields['args']}))

    return Translated()


RESOURCE_TRANSLATION: Mapping[str, Callable[[str], Tuple[str, str]]] = {
    'cpus': lambda cpus: ('cpu', cpus),
    'mem': lambda mem: ('memory', '{}Mi'.format(mem)),
    'disk': lambda disk: ('ephemeral-storage', '{}Mi'.format(disk)),
    'gpus': lambda gpus: ('nvidia.com/gpu', '{}'.format(gpus)),
}


def translate_resources(fields: Dict[str, Any]) -> Translated:
    app_requests = fields.copy()
    app_limits = app_requests.pop('resourceLimits', {})

    def iter_requests() -> Iterator[Tuple[str, str]]:
        for key, value in app_requests.items():
            if value != 0:
                yield RESOURCE_TRANSLATION[key](value)

    def iter_limits() -> Iterator[Tuple[str, str]]:
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


def translate_env(env: Mapping[str, Union[Dict[str, str], str]], app_secret_mapping: AppSecretMapping,
                  network_ports: Sequence[AppPort]) -> Translated:
    translated: List[Dict[str, Any]] = []
    not_translated = {}

    # FIXME: Sanitize against DCOS-specific stuff.
    for var, value in env.items():
        if isinstance(value, str):
            translated.append({"name": var, "value": value})
            continue

        if value.keys() != {'secret'}:
            not_translated[var] = value
            continue
        ref = app_secret_mapping.get_reference(value['secret'])

        translated.append({
            "name": var,
            "valueFrom": {
                'secretKeyRef': {
                    'name': ref.secret_name,
                    'key': ref.key,
                },
            },
        })

    if len(network_ports) > 0:
        all_ports = [str(effective_port(p)) for p in network_ports]

        # in case we're using PORTS we should append HOST=0.0.0.0
        # DC/OS fills it with the node IP address but for K8s this doesn't
        # make sense. So we fill it with 0.0.0.0 in case this var is used
        # for a bind
        translated.append({"name": "HOST", "value": "0.0.0.0"})

        translated.append({"name": "PORTS", "value": ",".join(all_ports)})
        for app_port in network_ports:
            port = effective_port(app_port)

            translated.append({"name": "PORT" + str(app_port.idx), "value": str(port)})
            if app_port.name:
                translated.append({"name": "PORT_" + app_port.name.upper(), "value": str(port)})

    return Translated(
        update=main_container({'env': translated}),
        warnings=["could not translate the following variables:\n" +
                  json.dumps(not_translated)] if not_translated else [],
    )


def marathon_app_id_to_k8s_app_id(marathon_app_id: str) -> str:
    """
    The de-facto method used to convert generate the app_id value used in the resulting StatefulSet / Deployment
    :param marathon_app_id: app_id as seen in the 'id' field for a Marathon app definition
    :return: Kubernetes app selector label value
    """
    app_id = marathon_app_id.strip('/')
    return utils.make_label(app_id)


def pod_selector_labels(marathon_app_id: str) -> Mapping[str, str]:
    return {'app': marathon_app_id_to_k8s_app_id(marathon_app_id)}


def translate_multitenancy(fields: Dict[str, Any]) -> Translated:
    # FIXME: Translate groups and roles.

    # TODO(asekretenko): Consider adding prefix or another label to show that
    # this has been generated by the DCOS migration script.
    marathon_app_id = fields['id']
    selector_labels = pod_selector_labels(fields['id'])
    return Translated(
        update={
            'metadata': {
                'name': utils.make_subdomain(marathon_app_id.strip('/').split('/')),
                'labels': selector_labels
            },
            'spec': {
                'selector': {
                    'matchLabels': selector_labels
                },
                'template': {
                    'metadata': {
                        'labels': selector_labels
                    }
                }
            }
        })


def get_network_probe_builder(get_port_by_index: Callable[[int, bool], int]) -> Callable[[Dict[str, Any]], Translated]:
    def build_network_probe(fields: Dict[str, Any]) -> Translated:
        protocol = fields.pop('protocol')
        port = fields.pop('port', None)
        index = fields.pop('portIndex', 0)
        path = fields.pop('path', '/')

        warnings = [] if not fields else \
            ['Non-translatable health check fields: {}'.format(
                try_oneline_dump(fields))]

        use_host_port = protocol in ['TCP', 'HTTP', 'HTTPS']
        port = get_port_by_index(index, use_host_port) if port is None else port

        # TODO (asekretenko): The app translator should choose a value for each port==0
        # once, and ensure that the same value is used for the same port
        # by different parts of the generated manifest.
        if port == 0:
            warnings.append("The app is using port 0 (auto-assigned by Marathon) in a health check."
                            " Please make sure that the generated K8s probe is using a correct port number.")

        if protocol in ['MESOS_TCP', 'TCP']:
            return Translated({'tcpSocket': {'port': port}}, warnings)

        if protocol in ['MESOS_HTTP', 'HTTP', 'MESOS_HTTPS', 'HTTPS']:
            scheme = 'HTTPS' if protocol in ['MESOS_HTTPS', 'HTTPS'] else 'HTTP'
            return Translated({'httpGet': {'port': port, 'scheme': scheme, 'path': path}}, warnings)

        raise InvalidAppDefinition("Invalid `protocol` in a health check: {}".format(protocol))

    return build_network_probe


def rename(name: str) -> Callable[[Dict[str, Any]], Translated]:
    return lambda _: Translated({name: _})


def readiness_check_to_probe(check: Dict[str, Any], error_location: str) -> Tuple[Dict[str, Any], List[str]]:
    def translate_http_get(fields: Dict[str, Any]) -> Translated:
        httpGet = {
            "port": fields["portName"],  # Marathon sets a default value of 'http-api' if not initially provided
            "path": fields["path"],  # Marathon sets a default value of '/' if not initially provided
            "scheme": fields[
                "protocol"],  # 'HTTP' or 'HTTPS' are allowed values by Marathon for this field. Marathon defaults to http when not provided.
        }
        return Translated({'httpGet': httpGet})

    mapping: Dict[MappingKey, Any] = {
        'name': skip_quietly,
        'intervalSeconds': rename('periodSeconds'),
        'timeoutSeconds': rename('timeoutSeconds'),
        ('protocol', 'path', 'portName'): translate_http_get,
        'httpStatusCodesForReady': skip_quietly,
        'preserveLastResponse': skip_quietly
    }

    probe, warnings = apply_mapping(mapping, check, error_location)
    warnings.append(
        "httpStatusCodesForReady are not translatable for readinessChecks, as Kubernetes considers any HTTP status 200-399 as successful."
    )

    return probe, warnings


def health_check_to_probe(check: Dict[str, Any], get_port_by_index: Callable[[int, bool], int],
                          error_location: str) -> Tuple[Dict[str, Any], List[str]]:
    flattened_check = flatten(check)

    mapping: Dict[MappingKey, Any] = {
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
        mapping['command.value'] = \
            lambda command: Translated(
                {'exec': {'command': ["/bin/sh", "-c", command]}})
    else:
        mapping[('protocol', 'port', 'portIndex', 'path')] = \
            get_network_probe_builder(get_port_by_index)

    probe, warnings = apply_mapping(mapping, flattened_check, error_location)
    probe.setdefault('initialDelaySeconds', 300)
    probe.setdefault('periodSeconds', 60)
    probe.setdefault('timeoutSeconds', 20)

    if check['protocol'] in ['TCP', 'HTTP', 'HTTPS']:
        warnings.append("The app is using a deprecated Marathon-level health check:\n" + try_oneline_dump(check) +
                        "\nPlease check that the K8s probe is using the correct port.")

    return probe, warnings


def translate_readiness_checks(readiness_checks: Sequence[Dict[str, Any]], error_location: str) -> Translated:
    if len(readiness_checks) < 1:
        return Translated()

    readiness_probe, warnings = readiness_check_to_probe(readiness_checks[0], error_location)

    # note: Marathon has never allowed more than one readiness check
    excess_readiness_checks = readiness_checks[1:]
    if excess_readiness_checks:
        warnings.append(
            'Error! More than one readiness check is defined. Marathon has never supported this. You should not see this message.'
        )

    return Translated(update=main_container({'readinessProbe': readiness_probe}), warnings=warnings)


def translate_health_checks(fields: Dict[str, Any], error_location: str) -> Translated:
    def get_port_by_index(index: int, use_host_port: bool = False) -> Any:
        port_mappings = fields.get('container', {}).get('portMappings')
        port_definitions = fields.get('portDefinitions')
        if (port_mappings is None) == (port_definitions is None):
            raise InvalidAppDefinition("Cannot get port by index as both portDefinitions"
                                       " and container.portMappings are set")

        if port_definitions is None:
            port_list, name = port_mappings, 'container.portMappings'
            key = 'hostPort' if use_host_port else 'containerPort'
        else:
            port_list, name = port_definitions, 'portDefinitions'
            key = 'port'

        try:
            port_data = port_list[index]
        except IndexError:
            raise InvalidAppDefinition("Port index {} used in a health check is missing from `{}`".format(index, name))

        try:
            return port_data[key]
        except KeyError:
            raise InvalidAppDefinition("`{}` contain no '{}' at index {} used in health check".format(
                name, key, index))

    health_checks = fields.get('healthChecks', [])
    if len(health_checks) < 1:
        return Translated()

    liveness_probe, warnings = health_check_to_probe(health_checks[0], get_port_by_index, error_location)

    excess_health_checks = health_checks[1:]
    if excess_health_checks:
        warnings.append('Only the first app health check is converted into a liveness probe.\n'
                        'Dropped health checks:\n{}'.format(try_oneline_dump(excess_health_checks)))

    return Translated(update=main_container({'livenessProbe': liveness_probe}), warnings=warnings)


def skip_quietly(_: Any) -> Translated:
    return Translated()


def not_translatable(_: Any) -> Translated:
    return Translated(warnings=["field not translatable"])


def skip_if_equals(default: Any) -> Callable[[Any], Translated]:
    if not default:
        return lambda value: Translated(warnings=[] if not value else
                                        ['Cannot translate non-empty value\n{}'.format(try_oneline_dump(value))])

    return lambda value: Translated(warnings=[] if value == default else [
        'A value\n{}\ndifferent from the default\n{}\ncannot be translated.'.format(
            try_oneline_dump(value), try_oneline_dump(default))
    ])


def translate_unreachable_strategy(strategy: Union[Dict[str, Any], str]) -> Translated:
    if isinstance(strategy, str):
        if strategy != "disabled":
            raise InvalidAppDefinition('Invalid "unreachableStatregy": {}'.format(strategy))

        return Translated(update=pod_spec_update({
            "tolerations":
            ListExtension([{
                "key": "node.kubernetes.io/unreachable",
                "operator": "Exists",
                "effect": "NoExecute",
            }])
        }),
                          warnings=['"unreachableStatregy" has been set to "disabled"'])

    fields = strategy.copy()
    try:
        inactive_after_seconds = fields.pop("inactiveAfterSeconds")
        expunge_after_seconds = fields.pop("expungeAfterSeconds")
    except KeyError as key:
        raise InvalidAppDefinition('"unreachableStatregy" missing {}'.format(key))

    if fields:
        return Translated(warnings=["Unknown fields: {}".format(try_oneline_dump(fields))])

    return Translated(
        update=pod_spec_update({
            "tolerations":
            ListExtension([{
                "key": "node.kubernetes.io/unreachable",
                "operator": "Exists",
                "effect": "NoExecute",
                "tolerationSeconds": expunge_after_seconds,
            }])
        }),
        warnings=[] if expunge_after_seconds == inactive_after_seconds else [
            'A value of "inactiveAfterSeconds" ({}) different from that of "expungeAfterSeconds"'
            ' ({}) has been ignored'.format(inactive_after_seconds, expunge_after_seconds)
        ],
    )


def translate_upgrade_strategy(strategy: Dict[str, Any]) -> Translated:
    fields = strategy.copy()
    try:
        maximum_over_capacity = fields.pop("maximumOverCapacity")
        minimum_health_capacity = fields.pop("minimumHealthCapacity")
    except KeyError as key:
        raise InvalidAppDefinition('"upgradeStatregy" missing {}'.format(key))

    if fields:
        return Translated(warnings=["Unknown fields: {}".format(try_oneline_dump(fields))])

    return Translated(update={
        "spec": {
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {
                    "maxUnavailable": "{}%".format(int(100.0 * (1.0 - minimum_health_capacity))),
                    "maxSurge": "{}%".format(int(100.0 * maximum_over_capacity))
                }
            }
        }
    },
                      warnings=[])


def get_constraint_translator(
        register_node_labels: Callable[[
            Set[str],
        ], None]) -> Callable[[
            Mapping[str, Any],
        ], Translated]:
    def translate(fields: Mapping[str, Any]) -> Translated:
        result, labels = translate_constraints(pod_selector_labels(fields['id']), fields.get('constraints', []))

        register_node_labels(labels)
        return result

    return translate


def generate_root_mapping(k8s_app_id: str, container_defaults: ContainerDefaults,
                          app_secrets_mapping: AppSecretMapping, error_location: str, network_ports: Sequence[AppPort],
                          register_node_labels: Callable[[
                              Set[str],
                          ], None], is_resident: bool) -> Dict[MappingKey, Any]:

    container_mappings: Dict[MappingKey, Any] = {
        ('args', 'cmd'): translate_container_command,
        ('backoffFactor', 'backoffSeconds'): skip_if_equals({
            'backoffFactor': 1.0,
            'backoffSeconds': 1.0
        }),
        ('constraints', 'id'): get_constraint_translator(register_node_labels),
        ('container', ): get_container_translator(k8s_app_id, container_defaults, app_secrets_mapping, error_location),
        ('cpus', 'mem', 'disk', 'gpus', 'resourceLimits'): translate_resources,
        'dependencies': skip_if_equals([]),
        'deployments': skip_quietly,
        ('env', ): lambda fields: translate_env(fields.get("env", {}), app_secrets_mapping, network_ports),
        'executor': skip_if_equals(""),
        'fetch': lambda fetches: translate_fetch(fetches, container_defaults, error_location),
        ('healthChecks', 'container', 'portDefinitions'):
        lambda fields: translate_health_checks(fields, error_location),
        'readinessChecks': lambda readinessChecks: translate_readiness_checks(readinessChecks, error_location),
        ('acceptedResourceRoles', 'id', 'role'): translate_multitenancy,
        'instances': lambda n: Translated(update={'spec': {
            'replicas': n
        }}),
        'killSelection': skip_if_equals("YOUNGEST_FIRST"),
        'ports': skip_if_equals(None),
        'labels': skip_if_equals({}),  # translate_labels,
        'maxLaunchDelaySeconds': skip_if_equals(300),
        ('networks', 'portDefinitions', 'requirePorts'): skip_quietly,  # translate_networking,
        'residency': skip_quietly,

        # 'secrets' do not map to anything and are used only in combination with other fields.
        'secrets': skip_quietly,
        'taskKillGracePeriodSeconds': lambda t: Translated(pod_spec_update({'terminationGracePeriodSeconds': t})),
        'tasksHealthy': skip_quietly,
        'tasksRunning': skip_quietly,
        'tasksStaged': skip_quietly,
        'tasksUnhealthy': skip_quietly,
        'unreachableStrategy': translate_unreachable_strategy,
        'upgradeStrategy': skip_quietly if is_resident else translate_upgrade_strategy,
        'user': skip_if_equals("nobody"),
        'version': skip_quietly,
        'versionInfo': skip_quietly,
    }

    all_mappings = {}
    all_mappings.update(container_mappings)
    return all_mappings


EXTRACT_COMMAND = dict([('.zip', 'gunzip')] + [(ext, 'tar -xf')
                                               for ext in ['.tgz', '.tar.gz', '.tbz2', '.tar.bz2', '.txz', '.tar.xz']])


def generate_fetch_command(uri: str, allow_extract: bool, executable: bool) -> str:
    # NOTE: The path separator is always '/', even on Windows.
    _, _, filename = uri.rpartition('/')
    _, ext = os.path.splitext(filename)

    postprocess = 'chmod a+x' if executable else \
        (EXTRACT_COMMAND.get(ext, '') if allow_extract else '')

    fmt = '( wget -O "{fn}" "{uri}" && {postprocess} "{fn}" )' if postprocess else\
          '( wget -O "{fn}" "{uri}")'

    return fmt.format(fn=filename, uri=uri, postprocess=postprocess)


def translate_fetch(fetches: Sequence[Dict[str, Any]], defaults: ContainerDefaults, error_location: str) -> Translated:
    if not defaults.working_dir:
        raise AdditionalFlagNeeded('{} is using "fetch"; please specify non-empty'
                                   ' `--container-working-dir` and run again'.format(error_location))

    warnings = ['This app uses "fetch"; consider using a container image instead.']

    def iter_command() -> Iterator[str]:
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
                warnings.append('Unknown fields in "fetch": {}'.format(json.dumps(fetch)))

            if cache:
                warnings.append('`cache=true` requested for fetching "{}" has been ignored'.format(uri))

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
                    "name": "fetch-artifacts",
                    "mountPath": "/fetch_artifacts"
                }],
                "workingDir": "/fetch_artifacts",
            }],
            "containers": [{
                "volumeMounts":
                ListExtension([{
                    "name": "fetch-artifacts",
                    "mountPath": defaults.working_dir,
                }]),
            }],
            "volumes":
            ListExtension([{
                "name": "fetch-artifacts",
                "emptyDir": {}
            }])
        }),
        warnings=warnings,
    )


def get_container_translator(
    k8s_app_id: str,
    defaults: ContainerDefaults,
    app_secret_mapping: AppSecretMapping,
    error_location: str,
) -> Callable[[Mapping[str, Any]], Translated]:
    def translate_image(image_fields: Mapping[MappingKey, Any]) -> Translated:
        if 'docker.image' in image_fields:
            return Translated(main_container({'image': image_fields['docker.image']}))

        if not defaults.image:
            raise AdditionalFlagNeeded('{} has no image; please specify non-empty'
                                       ' `--default-image` and run again'.format(error_location))
        container_update = {'image': defaults.image}

        # TODO (asekretenko): This sets 'workingDir' only if 'docker.image' is
        # not specified. Figure out how we want to treat a combination of
        # a 'fetch' with a non-default 'docker.image'.
        if defaults.working_dir:
            container_update['workingDir'] = defaults.working_dir
        return Translated(main_container(container_update))

    def translate_container(fields: Mapping[str, Any]) -> Translated:
        update, warnings = apply_mapping(mapping={
            "docker.forcePullImage":
            lambda _: Translated(main_container({'imagePullPolicy': "Always" if _ else "IfNotPresent"})),
            ("docker.image", ):
            translate_image,
            "docker.parameters":
            skip_if_equals([]),
            "docker.privileged":
            skip_if_equals(False),
            "docker.pullConfig.secret":
            lambda dcos_name: Translated(
                pod_spec_update(
                    {'imagePullSecrets': [{
                        'name': app_secret_mapping.get_image_pull_secret_name(dcos_name)
                    }]})),
            "linuxInfo":
            skip_if_equals({}),
            "portMappings":
            skip_quietly,
            "volumes":
            lambda _: volumes.translate_volumes(_, app_secret_mapping),
            "type":
            skip_quietly,
        },
                                         data=flatten(fields.get('container', {})),
                                         error_location=error_location + ", container")

        return Translated(update, warnings)

    return translate_container


def flatten(dictionary: Dict[str, Any]) -> Dict[str, Any]:
    """
    >>> flatten({'foo':{'bar':{'baz': 0}, 'deadbeef': 1}, '42': 3})
    {'foo.bar.baz': 0, 'foo.deadbeef': 1, '42': 3}
    """
    def iterate(data: Dict[str, Any], prefix: str) -> Iterator[Tuple[str, Any]]:
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


def load(path: str) -> List[Any]:
    with open(path) as input_file:
        apps = json.load(input_file)

    if isinstance(apps, list):
        return apps

    if not isinstance(apps, dict):
        raise InvalidInput("The top level of {} is neither a dict nor a list".format(path))

    if 'apps' in apps:
        return cast(List[Any], apps['apps'])

    log.warning("Interpreting %s as containing a single app", path)
    return [apps]


class TranslatedApp(NamedTuple):
    deployment: Dict[str, Any]
    warnings: List[str]
    required_node_labels: Set[str]


def translate_app(app: Dict[str, Any], settings: Settings) -> TranslatedApp:
    error_location = "app " + app.get('id', '(NO ID)')

    network_ports = get_ports_from_app(app)

    node_labels = set()
    register_node_labels = lambda labels: node_labels.update(labels)
    is_resident = volumes.is_resident(app)
    k8s_app_id = marathon_app_id_to_k8s_app_id(app['id'])

    mapping = generate_root_mapping(
        k8s_app_id,
        settings.container_defaults,
        settings.app_secret_mapping,
        error_location,
        network_ports,
        register_node_labels,
        is_resident,
    )

    try:
        deployment, warnings = apply_mapping(mapping, app, error_location)
    except InvalidAppDefinition as err:
        raise InvalidAppDefinition('{} at {}'.format(err, error_location))

    deployment = finalize_unmerged_list_extensions(deployment)

    if is_resident:
        deployment['spec']['volumeClaimTemplates'] = volumes.translate_volume_claim_templates(
            k8s_app_id, volumes.get_volumes(app))
        deployment['spec']['serviceName'] = k8s_app_id
        deployment.update({'apiVersion': 'apps/v1', 'kind': 'StatefulSet'})
        return TranslatedApp(deployment, warnings, node_labels)
    else:
        deployment.update({'apiVersion': 'apps/v1', 'kind': 'Deployment'})
        return TranslatedApp(deployment, warnings, node_labels)
