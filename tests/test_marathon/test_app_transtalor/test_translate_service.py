from typing import NamedTuple, Optional
from dcos_migrate.plugins.marathon import app_translator, service_translator
from dcos_migrate.plugins.marathon.service_translator import DCOS_IO_L4LB_NAME


def test_vip_translation_real_app_with_named_vip():
    postgres_app = app_translator.load("tests/test_marathon/test_app_transtalor/resources/nginx-vip-app.json")[0]
    result, warnings = service_translator.translate_service(postgres_app)

    assert (result['metadata']['labels'][DCOS_IO_L4LB_NAME] == 'nginx.marathon.l4lb.thisdcos.directory')
    assert (result["metadata"]["name"] == "nginx")
    assert (result["spec"]["selector"] == {'app': 'nginx'})
    assert (result["spec"]["ports"] == [
        {'name': 'http', 'port': 80, 'protocol': 'TCP'},
        {'name': 'https', 'port': 443, 'protocol': 'TCP'}
    ])
    assert ("clusterIP" not in result["spec"])


def test_vip_translation_static_ip():
    app = {
        "id": "my-app",
        "portDefinitions": [{
            "name": "http",
            "port": 0,
            "protocol": "tcp",
            "labels": {"VIP_0": "10.0.5.2:80"}
        }],
        "requirePorts": True
    }
    result, warnings = service_translator.translate_service(app)
    assert (result["spec"]["clusterIP"] == "10.0.5.2")


def test_host_auto_assign_ports():
    app = {
        "id": "my-app",
        "portDefinitions": [{
            "name": "http",
            "port": 0,
            "protocol": "tcp"
        }, {
            "name": "admin",
            "port": 0,
            "protocol": "tcp"
        }],
        "requirePorts": True
    }
    result, warnings = service_translator.translate_service(app)

    assert (result["metadata"]["name"] == "my-app")
    assert (result["spec"]["selector"] == {'app': 'my-app'})
    assert (result["spec"]["ports"][0] == {'name': "http", 'protocol': 'TCP', 'port': 10000})
    assert (result["spec"]["ports"][1] == {'name': "admin", 'protocol': 'TCP', 'port': 10001})


def test_vip_static_ip_port_definitions():
    app = {
        "id": "my-app",
        "portDefinitions": [{
            "name": "http",
            "port": 0,
            "labels": {"VIP_0": "1.2.3.4:80"},
            "protocol": "tcp"
        }],
        "requirePorts": True
    }
    result, warnings = service_translator.translate_service(app)

    assert (result["metadata"]["name"] == "my-app")
    assert (result["spec"]["selector"] == {'app': 'my-app'})
    assert (result["spec"]["ports"][0] == {'name': "http", 'targetPort': 10000, 'port': 80, 'protocol': 'TCP'})
    assert (result["spec"]["clusterIP"] == "1.2.3.4")


def test_take_container_port_value_when_host_port_is_auto():
    app = {
        "id": "my-app",
        "container": {
            "portMappings": [{
                "name": "http",
                "hostPort": 0,
                "containerPort": 80
            }]
        }
    }
    result, warnings = service_translator.translate_service(app)

    assert (result["metadata"]["name"] == "my-app")
    assert (result["spec"]["selector"] == {'app': 'my-app'})
    assert (result["spec"]["ports"][0] == {'name': "http", 'port': 80, 'protocol': 'TCP'})


def test_vip_static_ip_port_mappings():
    app = {
        "id": "my-app",
        "container": {
            "portMappings": [{
                "name": "http",
                "hostPort": 0,
                "containerPort": 0,
                "labels": {"VIP_0": "1.2.3.4:80"},
                "protocol": "tcp"
            }]
        }
    }
    result, warnings = service_translator.translate_service(app)

    assert (result["metadata"]["name"] == "my-app")
    assert (result["spec"]["selector"] == {'app': 'my-app'})
    assert (result["spec"]["ports"][0] == {'name': "http", 'targetPort': 10000, 'port': 80, 'protocol': 'TCP'})
    assert (result["spec"]["clusterIP"] == "1.2.3.4")


def test_old_l4lb_address_translation():
    app = {
        "id": "my-app",
        "container": {
            "portMappings": [{
                "name": "http",
                "hostPort": 0,
                "containerPort": 0,
                "labels": {"VIP_0": "/testing.subdomain:80"},
                "protocol": "tcp"
            }]
        }
    }
    result, warnings = service_translator.translate_service(app)
    assert (result['metadata']['labels'][DCOS_IO_L4LB_NAME] == 'testing.subdomain.marathon.l4lb.thisdcos.directory')


def test_require_ports_false_for_port_definitions_leads_to_auto_port():
    app = {
        "id": "my-app",
        "portDefinitions": [{
            "name": "http",
            "port": 10104,
            "protocol": "tcp"
        }, {
            "name": "admin",
            "port": 10105,
            "protocol": "tcp"
        }],
        "requirePorts": False
    }
    result, warnings = service_translator.translate_service(app)
    assert (result["spec"]["ports"][0] == {'name': "http", 'protocol': 'TCP', 'port': 10000})
    assert (result["spec"]["ports"][1] == {'name': "admin", 'protocol': 'TCP', 'port': 10001})


def test_protocol_is_copied_over():
    app = {
        "id": "my-app",
        "portDefinitions": [{
            "name": "tcp",
            "port": 80,
            "protocol": "tcp"
        }, {
            "name": "default",
            "port": 443
        }, {
            "name": "udp",
            "port": 8080,
            "protocol": "udp"
        }, {
            "name": "both",
            "port": 8081,
            "protocol": "udp,tcp"
        }],
        "requirePorts": True
    }
    result, warnings = service_translator.translate_service(app)
    assert (result["spec"]["ports"][0] == {'name': "tcp", 'protocol': 'TCP', 'port': 80})
    assert (result["spec"]["ports"][1] == {'name': "default", 'protocol': 'TCP', 'port': 443})
    assert (result["spec"]["ports"][2] == {'name': "udp", 'protocol': 'UDP', 'port': 8080})
    assert (result["spec"]["ports"][3] == {'name': "both", 'protocol': 'UDP', 'port': 8081})
    assert (result["spec"]["ports"][4] == {'name': "both", 'protocol': 'TCP', 'port': 8081})


def test_warnings_generated_for_conflicting_ports():
    app = {
        "id": "my-app",
        "portDefinitions": [{
            "name": "auto",
            "port": 0,
            "protocol": "tcp"
        }, {
            "name": "static",
            "port": 10000
        }],
        "requirePorts": True
    }
    [_, warnings] = service_translator.translate_service(app)
    assert (warnings == [
        "Port 'auto' and port 'static' conflict. This is probably due to the service having a mix of auto-assigned "
        "ports."])


def test_warnings_invalid_protocol():
    # This should never happen as Marathon validates the protocol list to be tcp or udp; but, just in case!
    app = {
        "id": "my-app",
        "portDefinitions": [{
            "name": "http",
            "port": 8080,
            "protocol": "bad"
        }],
        "requirePorts": True
    }
    [result, warnings] = service_translator.translate_service(app)
    assert (result["spec"]["ports"][0] == {'name': "http", 'protocol': 'TCP', 'port': 8080})
    assert (warnings == ['Protocol "bad" for port "http" is invalid; assuming TCP'])
