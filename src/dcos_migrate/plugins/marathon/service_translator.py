from .network_helpers import get_ports_from_app, effective_port, AppPort
from typing import Sequence, Tuple, Any, Optional, Dict, TypedDict, List, Set
import ipaddress
from dcos_migrate import utils

DCOS_IO_L4LB_NAME = "dcos.io/l4lb-dns"

HOST_NETWORKING_WARNING = 'Host networking is not supported in Kubernetes. You may wish to convert this service to a ' \
                          'nodePort so outside traffic can reach it. '


def __is_ip_address(vip_name: str) -> bool:
    try:
        ipaddress.ip_address(vip_name)
        return True
    except ValueError:
        return False


class K8sPort(TypedDict, total=False):
    name: str
    port: int
    protocol: str
    targetPort: int


def dcosl4lb_name(vip_name: str) -> str:
    # TODO - allow customization of framework name for MoM migration
    if vip_name.startswith("/"):
        vip_name = vip_name[1:]
    return vip_name + ".marathon.l4lb.thisdcos.directory"


def __check_conflicts(app_ports: Sequence[AppPort]) -> Sequence[str]:
    warnings = []
    for i, a in enumerate(app_ports):
        for b in app_ports[i + 1:]:
            if effective_port(a) == effective_port(b):
                warnings.append("Port '{}' and port '{}' conflict. "
                                "This is probably due to the service having a mix of auto-assigned ports.".format(
                                    a.name, b.name))
    return warnings


def __convert_k8s_ports(app_ports: Sequence[AppPort]) -> Tuple[Sequence[str], Sequence[K8sPort]]:
    service_ports: List[K8sPort] = []
    warnings = list(__check_conflicts(app_ports))

    for port in app_ports:
        port.protocols
        for protocol in port.protocols:
            if protocol not in ["udp", "tcp"]:
                warnings.append('Protocol "{}" for port "{}" is invalid; assuming TCP'.format(protocol, port.name))
                protocol = "TCP"

            source_port = effective_port(port)
            service_port: K8sPort = {"port": source_port, "protocol": protocol.upper()}
            if port.containerPort != source_port:
                service_port["targetPort"] = port.containerPort

            if port.name:
                service_port["name"] = utils.make_label(port.name)

            service_ports.append(service_port)
    return warnings, service_ports


def __infer_static_ip(app_ports: Sequence[AppPort]) -> Tuple[Sequence[str], Optional[str]]:
    static_ips: Set[str] = set(port.vip.name for port in app_ports if port.vip and __is_ip_address(port.vip.name))

    static_cluster_ip: Optional[str]

    if len(static_ips) == 1:
        [static_cluster_ip] = static_ips
        return [], static_cluster_ip
    elif len(static_ips) == 0:
        return [], None
    else:
        return ["Multiple static ips for a single service is not supported"], None


def __infer_former_l4lb_name(app_ports: Sequence[AppPort]) -> Tuple[Sequence[str], Optional[str]]:
    former_l4lb_dns_names = set(
        [dcosl4lb_name(port.vip.name) for port in app_ports if port.vip and not __is_ip_address(port.vip.name)])

    if len(former_l4lb_dns_names) == 1:
        [former_l4lb_dns] = former_l4lb_dns_names
        return [], former_l4lb_dns
    elif len(former_l4lb_dns_names) == 0:
        return [], None
    else:
        return ["Multiple vips {} for a single service is not supported by the migration tool. "
                "You'll need to manually create the services if needed.".format(",".join(former_l4lb_dns_names))],\
               None


def __get_network_modes_from_app(app: Dict[str, Any]) -> Set[str]:
    if "networks" in app:
        n: Sequence[str] = [network["mode"] for network in app["networks"]]
        return set(n)
    else:
        return set()


def translate_service(app_label: str, app: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Sequence[str]]:
    app_ports = get_ports_from_app(app)
    network_modes = __get_network_modes_from_app(app)
    if len(app_ports) == 0 and network_modes == set(["container/bridge"]):
        # If no ports are defined, and this used container/bridge networking, then nothing talked to this service.
        # Return no service in this case
        return None, []
    else:
        warnings: List[str] = []
        port_warnings, service_ports = __convert_k8s_ports(app_ports)
        warnings += port_warnings

        static_ip_warning, static_cluster_ip = __infer_static_ip(app_ports)
        warnings += static_ip_warning

        l4lb_dns_warnings, former_l4lb_dns = __infer_former_l4lb_name(app_ports)
        warnings += l4lb_dns_warnings

        if "host" in network_modes:
            warnings += [HOST_NETWORKING_WARNING]

        service_spec: Dict[str, Any] = {"type": "ClusterIP", "selector": {"app": app_label}, "ports": service_ports}

        if static_cluster_ip:
            service_spec["clusterIP"] = static_cluster_ip
        elif len(service_ports) == 0:
            service_spec["clusterIP"] = "None"

        metadata: Dict[str, Any] = {"name": app_label}
        if former_l4lb_dns:
            metadata["labels"] = {DCOS_IO_L4LB_NAME: former_l4lb_dns}
        api_version = "v1"
        kind = "Service"

        return {"apiVersion": api_version, "kind": kind, "metadata": metadata, "spec": service_spec}, warnings
