#

import warnings
from typing import Any, Dict, Optional

BALANCE_WARNING = (
    "Backend {} uses a haproxy balance method {}, " "forcing to `roundrobin`."
)

MAP_HOST_WARNING = (
    "Frontend {} map contains multiple host matches, "
    "only `hostReg` will be used. ({})"
)

MAP_PATH_WARNING = (
    "Frontend {} map contains multiple path matches, "
    "only `pathReg` will be used. ({})"
)

MISC_WARNING = (
    "{} {} contains `miscStrs`, "
    "these cannot be auto migrated, please inspect "
    "the final configuration and configure as needed."
)

NO_SERVICES_WARNING = (
    "Backend {} contains more no service entry. "
    "Backend will not be migrated."
)

MULTIPLE_SERVICE_WARNING = (
    "Backend {} contains more than one service entry ({}). "
    "Only the first one will be used."
)

PORT_WARNING = (
    "Backend {} does not use a portName for the endpoint. "
    "The appropriate port name must be added manually."
)

TCP_WARNING = (
    "Frontend for port {} is not HTTP/HTTPs, "
    "cannot auto migrate to traefik 1.7."
)

V1_WARNING = "{}: EdgeLB V1 Pool format detected, only V2 is supported."


def parse_backend(backend: Dict[str, Any]) -> Dict[str, Any]:
    name = backend["name"]
    services = backend["services"]

    if not services:
        warnings.warn(NO_SERVICES_WARNING.format(name))

    if len(services) > 1:
        warnings.warn(MULTIPLE_SERVICE_WARNING.format(name, len(services)))

    if backend.get("miscStrs"):
        warnings.warn(MISC_WARNING.format("Backend", name))

    if backend.get("balance", "roundrobin") != "roundrobin":
        warnings.warn(BALANCE_WARNING.format(name, backend.get("balance")))

    service = services[0]
    endpoint = service["endpoint"]

    port = endpoint.get("portName")
    if not port:
        warnings.warn(PORT_WARNING.format(name))
        port = str(endpoint.get("port"))

    # TODO(jkoelker) is it possible to determine the mesos service endpoints?
    service_name = service.get("marathon", {}).get("serviceID")
    if service_name:
        service_name = service_name.lstrip("/").replace("/", ".")
    else:
        service_name = "UNKNOWN"

    # TODO(jkoelker) handle rewriting requests?
    return {
        "balance": "roundrobin",
        "service": {
            "port": port,
            "name": service_name,
        },
    }


def parse_map(frontend_name: str, m: Dict[str, Any]) -> Dict[str, Any]:
    ret = {"backend": m["backend"]}

    if "hostReg" in m:
        if "hostEq" in m:
            warnings.warn(MAP_HOST_WARNING.format(frontend_name, m))
        ret["host"] = m["hostReg"]

    elif "hostEq" in m:
        ret["host"] = m["hostEq"]

    if "pathReg" in m:
        if "pathBeg" or "pathEnd" in m:
            warnings.warn(MAP_PATH_WARNING.format(frontend_name, m))
        ret["path"] = m["pathReg"]

    elif "pathBeg" and "pathEnd" in m:
        ret["path"] = "{}.*{}".format(m["pathBeg"], m["pathEnd"])

    elif "pathBeg" in m:
        ret["path"] = "{}.*".format(m["pathBeg"])

    elif "pathEnd" in m:
        ret["path"] = "{}.*".format(m["pathEnd"])

    return ret


def parse_pool(pool: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if pool.get("apiVersion") != "V2":
        warnings.warn(V1_WARNING.format(pool.get("name", "unknown")))
        return None

    name = pool["name"]
    haproxy = pool["haproxy"]

    autopool = False
    if name[:5] == "auto-":
        autopool = True

    backends = {b["name"]: parse_backend(b) for b in haproxy["backends"]}
    frontends = {}

    for frontend in haproxy["frontends"]:
        if "HTTP" not in frontend["protocol"]:
            warnings.warn(TCP_WARNING.format(frontend["bindPort"]))

        if frontend.get("miscStrs"):
            warnings.warn(
                MISC_WARNING.format("Frontend", pool.get("name", "unknown"))
            )

        link_backend = frontend["linkBackend"]
        frontend_name = frontend.get("name")
        if not frontend_name:
            frontend_name = "frontend_{}_{}".format(
                frontend.get("bindAddress", "0.0.0.0"),
                frontend.get("bindPort", 0),
            )

        frontends[frontend["bindPort"]] = {
            "name": frontend_name,
            "port": frontend["bindPort"],
            "protocol": frontend["protocol"],
            "certificates": frontend.get("certificates", []),
            "default_backend": link_backend.get("defaultBackend"),
            "rules": [parse_map(name, m) for m in link_backend.get("map", [])],
        }

    return {
        "autoCertificate": pool.get("autoCertificate", False),
        "autopool": autopool,
        "name": name,
        "namespace": pool.get("namespace"),
        "secrets": pool.get("secrets", []),
        "frontends": frontends,
        "backends": backends,
    }
