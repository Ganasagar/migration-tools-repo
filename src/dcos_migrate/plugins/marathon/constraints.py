import abc
import re
from typing import Any, List, Mapping, Sequence, Set, Tuple

from collections import defaultdict

import dcos_migrate.utils as utils

from .common import pod_spec_update
from .mapping_utils import Translated


def translate_constraints(
    app_pod_labels: Mapping[str, str],
    constraints: List[List[Any]],
) -> Tuple[Translated, Set[str]]:

    mappers: List[_ConstraintMapper] = [
        _PodAntiAffinityMapper(app_pod_labels),
        _TopologySpreadMapper(app_pod_labels),
        _NodeSelectorMapper()
    ]

    warnings = []
    for constraint in constraints:
        if all(not m.consume(constraint) for m in mappers):
            warnings.append("Constraint {} could not be translated".format(constraint))

    all_node_labels = set()
    result = Translated(warnings=warnings)
    for mapper in mappers:
        migrated, node_labels = mapper.result()
        result = result.merged_with(migrated)
        all_node_labels |= node_labels

    return result, all_node_labels


class _ConstraintMapper(abc.ABC):
    @abc.abstractmethod
    def consume(self, constraint: List[Any]) -> bool:
        """Returns True if this mapper can translate this constraint."""
        pass

    @abc.abstractmethod
    def result(self, ) -> Tuple[Translated, Set[str]]:
        """
        Returns constraint translation result and K8s node labels that need
        to be present to run the deployment.
        """
        pass


def _is_unique_hostname_constraint(constraint: List[str]) -> bool:
    return constraint[1] == "UNIQUE" and constraint[0] in ("hostname", "@hostname")


class _PodAntiAffinityMapper(_ConstraintMapper):
    """
    ["@hostname", "UNIQUE"] maps directly onto podAntiaffinity;
    this class provides exactly this mapping.
    """
    def __init__(self, app_pod_labels: Mapping[str, str]):
        self._app_pod_labels = app_pod_labels
        self._result: Tuple[Translated, Set[str]] = (Translated(), set())

    def consume(self, constraint: List[Any]) -> bool:
        if not _is_unique_hostname_constraint(constraint):
            return False

        self._result = (Translated(
            pod_spec_update({
                "affinity": {
                    "podAntiAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": [{
                            "labelSelector": {
                                "matchLabels": self._app_pod_labels
                            },
                            "topologyKey": "kubernetes.io/hostname",
                        }],
                    }
                }
            })), {
                "kubernetes.io/hostname",
            })
        return True

    def result(self) -> Tuple[Translated, Set[str]]:
        return self._result


class _TopologySpreadMapper(_ConstraintMapper):
    """
    Handles Marathon constraints that can be approximated by K8s topologySpreadConstraints.
    """
    def __init__(self, app_pod_labels: Mapping[str, str]):
        self._app_pod_labels = app_pod_labels
        self._topology_fields: List[str] = []

    def consume(self, constraint: List[Any]) -> bool:
        if constraint[1] not in ("UNIQUE", "MAX_PER") or\
            _is_unique_hostname_constraint(constraint):
            return False

        self._topology_fields.append(constraint[0])
        return True

    __SPECIAL_FIELD_MAPPING = {
        "hostname": "kubernetes.io/hostname",
        "@hostname": "kubernetes.io/hostname",
        "@region": "topology.kubernetes.io/region",
        "@zone": "topology.kubernetes.io/zone",
    }

    def result(self) -> Tuple[Translated, Set[str]]:
        if not self._topology_fields:
            return Translated(), set()

        node_labels = set()
        topology_spread_constraints = []

        for field in self._topology_fields:
            try:
                topology_key = self.__SPECIAL_FIELD_MAPPING[field]
            except KeyError:
                # TODO: Consider prefixing required custom labels
                topology_key = utils.make_label(field)

            node_labels.add(topology_key)
            topology_spread_constraints.append({
                "maxSkew": 1,
                "topologyKey": topology_key,
                "whenUnsatisfiable": "DoNotSchedule",
                "labelSelector": {
                    "matchLabels": self._app_pod_labels
                },
            })

        return (
            Translated(update=pod_spec_update({"topologySpreadConstraints": topology_spread_constraints}),
                       warnings=[
                           " Please check that topologySpreadConstraints generated from UNIQUE/MAX_PER"
                           " are correct for your use case."
                       ]),
            node_labels,
        )


NO_CONTROL_CHARACTER_REGEX = re.compile(r'^(?:\w|\s)*$')


class _NodeSelectorMapper(_ConstraintMapper):
    """
    Handles Marathon constraints that map onto K8s nodeSelector.
    """
    def __init__(self) -> None:
        self._label_values: Mapping[str, Set[str]] = defaultdict(set)

    __FORMER_DCOS_HOSTNAME_LABEL = "dcos.io/former-dcos-hostname"

    __SPECIAL_FIELD_MAPPING = {
        "hostname": __FORMER_DCOS_HOSTNAME_LABEL,
        "@hostname": __FORMER_DCOS_HOSTNAME_LABEL,
        "@region": "topology.kubernetes.io/region",
        "@zone": "topology.kubernetes.io/zone",
    }

    def consume(self, constraint: List[Any]) -> bool:
        try:
            [field, operator, value] = constraint
        except ValueError:
            return False

        if operator not in ("IS", "LIKE"):
            return False

        if operator == "LIKE" and not NO_CONTROL_CHARACTER_REGEX.match(value):
            return False

        label = self.__SPECIAL_FIELD_MAPPING.get(field, utils.make_label(field))
        self._label_values[label].add(value)
        return True

    def result(self) -> Tuple[Translated, Set[str]]:
        node_selector = {}
        warnings = []
        for label, values in self._label_values.items():
            node_selector[label] = utils.make_label(next(iter(values)))
            if len(values) > 1:
                warnings.append("App constraints result in conflicting values"
                                " for label '{}': {}".format(label, values))

        if self.__FORMER_DCOS_HOSTNAME_LABEL in node_selector:
            warnings.append("The app sets a constraint on hostname value; make sure that label {} "
                            " is set on nodes".format(self.__FORMER_DCOS_HOSTNAME_LABEL))

        return (
            Translated(update=pod_spec_update({"nodeSelector": node_selector}), warnings=warnings),
            set(node_selector),
        )
