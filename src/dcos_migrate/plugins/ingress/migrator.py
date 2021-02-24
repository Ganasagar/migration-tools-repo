#

import warnings
from typing import Any, Dict, List, Optional, Union

from kubernetes.client import models  # type: ignore

from dcos_migrate import system


FRONTEND_PORT_WARNING = (
    "Frontend {} uses a port other than 80/443. Please edit the input to map "
    "it to an HTTP/HTTPS site."
)

TCP_BACKEND_WARNING = (
    "Frontend {} does not specify or specifies an invalid default backend."
)


def migrate_ingress(pool: Dict[str, Any]) -> Optional[models.ExtensionsV1beta1Ingress]:
    rules = []

    backends = pool.get("backends", {})
    frontends = pool.get("frontends", {})

    for frontend in frontends.values():
        if "HTTP" not in frontend.get("protocol").upper():
            # NOTE(jkoelker) don't migrate a non-http frontend to ingress
            continue

        if frontend.get("port") not in (80, 443):
            warnings.warn(
                FRONTEND_PORT_WARNING.format(frontend.get("name", "UNKNOWN"))
            )

        frontend_rules = frontend.get("rules")
        if not frontend_rules:
            frontend_rules = [{"backend": frontend.get("default_backend")}]

        for rule in frontend_rules:
            backend = backends.get(rule["backend"], {})

            path = models.ExtensionsV1beta1HTTPIngressPath(
                path=rule.get("path", "/"),
                backend=models.ExtensionsV1beta1IngressBackend(
                    service_name=backend["service"]["name"],
                    service_port=backend["service"]["port"],
                ),
            )

            r = models.ExtensionsV1beta1IngressRule(
                host=rule.get("host"),
                http=models.ExtensionsV1beta1HTTPIngressRuleValue(
                    paths=[path],
                ),
            )

            rules.append(r)

    if not rules:
        return None

    spec = {
        "rules": rules,
    }
    spec = models.ExtensionsV1beta1IngressSpec(rules=rules)

    metadata = models.V1ObjectMeta(
        annotations={},
        name=pool["name"],
        namespace=pool.get("namespace"),
    )
    metadata.annotations["kubernetes.io/ingress.class"] = "traefik"

    ingress = models.ExtensionsV1beta1Ingress(
        api_version="extensions/v1beta1",
        kind="Ingress",
        metadata=metadata,
        spec=spec,
    )

    return ingress


def migrate_lb(pool: Dict[str, Any]) -> List[models.V1Service]:
    output = []

    backends = pool.get("backends", {})
    frontends = pool.get("frontends", {})

    for frontend in frontends.values():
        if "HTTP" in frontend.get("protocol").upper():
            continue

        backend = backends.get(frontend.get("default_backend"))

        if not backend:
            warnings.warn(
                TCP_BACKEND_WARNING.format(frontend.get("name", "UNKNOWN"))
            )
            continue

        # TODO(jkoelker) figure out targetPort
        port = models.V1ServicePort(
            port=frontend["port"],
            target_port=0,
            protocol=frontend.get("protocol").upper(),
        )
        spec = models.V1ServiceSpec(
            type="LoadBalancer",
            ports=[port],
            selector={
                "app": backend["service"]["name"],
            },
        )

        metadata = models.V1ObjectMeta(
            annotations={},
            name=pool["name"],
            namespace=pool.get("namespace"),
        )

        lb = models.V1Service(
            api_version="v1",
            kind="Service",
            metadata=metadata,
            spec=spec,
        )

        output.append(lb)

    return output


def migrate(pool: Dict[str, Any]) -> List[Union[models.ExtensionsV1beta1Ingress, models.V1Service]]:
    # TODO(jkoelker) handle non-ingress ports for http traffic
    ingress = migrate_ingress(pool)
    if ingress is None:
        output = []
    else:
        output = [ingress]
    output.extend(migrate_lb(pool))

    return output


class Ingress(system.Migrator):
    def __init__(self, *args: Any, **kwargs: Any):
        super(Ingress, self).__init__(*args, **kwargs)
        self.translate = {
            "name": self.translate_pool,
        }

    def translate_pool(self, key: str, value: str, full_path: str) -> None:
        assert self.object is not None
        objects = migrate(self.object)

        cluster_annotations = {}
        assert self.manifest_list is not None
        cluster_metadata = self.manifest_list.clusterMeta()
        if cluster_metadata is not None and cluster_metadata.annotations:
            cluster_annotations = cluster_metadata.annotations

        if not any(objects):
            return

        self.manifest = system.Manifest(
            pluginName="ingress",
            manifestName=self.dnsify(value),
        )

        assert self.manifest is not None
        for obj in objects:
            if not obj:
                continue

            if obj.metadata:
                obj.metadata.annotations.update(cluster_annotations)
            else:
                obj.metadata = models.V1ObjectMeta(
                    annotations=cluster_annotations,
                )

            self.manifest.append(obj)
