from .network_helpers import get_ports_from_app, effective_port, AppPort
from typing import Sequence, Tuple, Any, Optional, Dict
import dcos_migrate.utils as utils
import logging
import ipaddress


DCOS_IO_L4LB_NAME = "dcos.io/l4lb-dns"


def __is_ip_address(vip_name: str) -> bool:
    try:
        ipaddress.ip_address(vip_name)
        return True
    except ValueError:
        return False


def dcosl4lb_name(vip_name: str) -> str:
    # TODO - allow customization of framework name for MoM migration
    if vip_name.startswith("/"):
        vip_name = vip_name[1:]
    return vip_name + ".marathon.l4lb.thisdcos.directory"


def __check_conflicts(app_id: str, app_ports: Sequence[AppPort]) -> Sequence[str]:
    warnings = []
    for i, a in enumerate(app_ports):
        for b in app_ports[i+1:]:
            if effective_port(a) == effective_port(b):
                warnings.append(
                    "Port '{}' and port '{}' conflict. "
                    "This is probably due to the service having a mix of auto-assigned ports.".format(
                        a.name,
                        b.name))
    return warnings


def translate_service(app: Dict[str, Any]) -> Tuple[Dict[str, Any], Sequence[str]]:
    app_id = utils.dnsify(app['id'])

    service_ports = []
    app_ports = get_ports_from_app(app)
    warnings = list(__check_conflicts(app_id, app_ports))
    for port in app_ports:
        for protocol in port.protocols:
            if protocol not in ["udp", "tcp"]:
                warnings.append('Protocol "{}" for port "{}" is invalid; assuming TCP'.format(protocol, port.name))
                protocol = "TCP"

            source_port = effective_port(port)
            service_port = {
                "port": source_port,
                "protocol": protocol.upper()
            }
            if port.containerPort != source_port:
                service_port["targetPort"] = port.containerPort

            if port.name:
                service_port["name"] = port.name

            service_ports.append(service_port)

    static_ips = set(port.vip.name for port in app_ports if port.vip and __is_ip_address(port.vip.name))

    static_cluster_ip: Optional[str]

    if len(static_ips) == 1:
        [static_cluster_ip] = static_ips
    elif len(static_ips) == 0:
        static_cluster_ip = None
    else:
        static_cluster_ip = None
        logging.warning("Multiple static ips for a single service is not supported")

    former_l4lb_dns_names = set([dcosl4lb_name(port.vip.name) for port in app_ports if port.vip and not __is_ip_address(port.vip.name)])

    former_l4lb_dns: Optional[str]

    if len(former_l4lb_dns_names) == 1:
        [former_l4lb_dns] = former_l4lb_dns_names
    elif len(former_l4lb_dns_names) == 0:
        former_l4lb_dns = None
    else:
        former_l4lb_dns = None
        logging.warning("Multiple static ips for a single service is not supported")

    service_spec: Dict[str, Any] = {
        "type": "ClusterIP",
        "selector": {
            "app": app_id
        },
        "ports": service_ports
    }
    if static_cluster_ip:
        service_spec["clusterIP"] = static_cluster_ip

    metadata: Dict[str, Any] = {"name": app_id, "labels": {}}
    if former_l4lb_dns:
        metadata["labels"][DCOS_IO_L4LB_NAME] = former_l4lb_dns
    api_version = "v1"
    kind = "Service"

    return {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": metadata,
        "spec": service_spec
    }, warnings
