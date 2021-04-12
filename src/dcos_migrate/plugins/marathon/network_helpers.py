from typing import NamedTuple, Optional, Sequence, Any, Dict
import logging

PORT_AUTOASSIGN_START = 10000


class Vip(NamedTuple):
    name: str
    port: int


class AppPort(NamedTuple):
    name: Optional[str]
    protocols: Sequence[str]
    port: int
    containerPort: int
    vip: Optional[Vip]
    idx: int


def __autoport(port: Optional[int], index: int) -> int:
    if (port is None) or (port == 0):
        return PORT_AUTOASSIGN_START + index
    else:
        return port


def __get_vip_from_labels(labels: Dict[str, str]) -> Optional[Vip]:
    vip = None
    for (lKey, lValue) in labels.items():
        if lKey.startswith("VIP_"):
            if vip is not None:
                logging.warning("Multiple VIP labels for a portDefinition are not supported")
            [vip_name, vip_port] = lValue.split(":")
            vip = Vip(vip_name, int(vip_port))
    return vip


def __parse_protocols(protocol: Optional[str]) -> Sequence[str]:
    if protocol is None:
        return ["tcp"]
    else:
        return protocol.split(",")


def __derive_port_from_port_mapping(port_mapping: Dict[str, Any], index: int) -> AppPort:
    most_specific_port = port_mapping.get("hostPort") or port_mapping.get("containerPort") or __autoport(0, index)
    port = port_mapping.get("hostPort") or most_specific_port
    containerPort = port_mapping.get("containerPort") or most_specific_port
    name = port_mapping.get("name")
    vip = __get_vip_from_labels(port_mapping.get("labels", {}))

    # Marathon validates portMappings[].protocol to be either "tcp" or "udp"
    protocols = __parse_protocols(port_mapping.get("protocol"))

    return AppPort(name=name, port=port, containerPort=containerPort, vip=vip, idx=index, protocols=protocols)


def __derive_port_from_port_definition(port_definition: Dict[str, Any], index: int, require_ports: bool) -> AppPort:
    if require_ports:
        port = __autoport(port_definition.get("port"), index)
    else:
        port = __autoport(0, index)
    name = port_definition.get("name")
    vip = __get_vip_from_labels(port_definition.get("labels", {}))
    protocols = __parse_protocols(port_definition.get("protocol"))

    return AppPort(name=name, port=port, containerPort=port, vip=vip, idx=index, protocols=protocols)


def effective_port(port: AppPort) -> int:
    if port.vip:
        return port.vip.port
    else:
        return port.port


def get_ports_from_app(app: Dict[str, Any]) -> Sequence[AppPort]:
    if "portDefinitions" in app:
        require_ports = app.get("requirePorts", False)
        return [
            __derive_port_from_port_definition(port_definition, i, require_ports)
            for i, port_definition in enumerate(app["portDefinitions"])
        ]
    elif "container" in app and "portMappings" in app["container"]:
        return [
            __derive_port_from_port_mapping(port_mapping, i)
            for i, port_mapping in enumerate(app["container"]["portMappings"])
        ]
    else:
        return []
