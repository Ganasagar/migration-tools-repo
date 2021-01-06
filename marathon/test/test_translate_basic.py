from ..lib import app_translator
import os
import sys

import pytest

def new_settings(image: str = "busybox"):
    return app_translator.Settings(
        app_translator.ContainerDefaults(
            image=image,
            working_dir=".",
        ),
        imported_k8s_secret_name = "dummy"
    )



def test_happy_path_sleeper():
    settings = new_settings()
    hello_app = app_translator.load("test/resources/simple-command-app.json")[0]
    result, warnings = app_translator.translate_app(hello_app, settings)

    assert(result['kind'] == "Deployment")
    assert(result['metadata']['name'] == "sleep")
    assert(result['metadata']['labels'] == {'app': 'sleep'})
    assert(result['spec']['replicas'] == 10)
    container = result['spec']['template']['spec']['containers'][0]

    assert(container['command'] == ['/bin/sh', '-c', 'sleep 3600'])
    assert(container['image'] == 'busybox')
    assert(container['resources'] == {
        'requests': {'cpu': 0.01, 'memory': '64Mi'},
        'limits': {'cpu': 0.01, 'memory': '64Mi'}})

    assert(container['name'] == 'main')


@pytest.mark.parametrize('app_resource_fields,expected_k8s_resources', [
    ({}, {}),
    ({'cpus': 0.0}, {}),
    (
        {'cpus': 1},
        {'requests': {'cpu': 1}, 'limits': {'cpu': 1}},
    ),
    (
        {'cpus': 1, 'resourceLimits': {'cpus': "unlimited"}},
        {'requests': {'cpu': 1}}
    ),
    (
        {'cpus': 1, 'resourceLimits': {'cpus': 2}},
        {'requests': {'cpu': 1}, 'limits': {'cpu': 2}}
    ),
    (
        {'cpus': 0, 'resourceLimits': {'cpus': 3}},
        {'limits': {'cpu': 3}}
    ),
    (
        {'resourceLimits': {'cpus': 4}},
        {'limits': {'cpu': 4}}
    ),
    (
        {'mem': 128, 'resourceLimits': {'cpus': 4}},
        {'requests': {'memory': '128Mi'}, 'limits': {'memory': '128Mi', 'cpu': 4}}
    ),

])
def test_resource_requests_and_limits(app_resource_fields, expected_k8s_resources):
    settings = new_settings()
    app = {"id":"app"}
    app.update(app_resource_fields)
    result, _ = app_translator.translate_app(app, settings)
    resources = result['spec']['template']['spec']['containers'][0]['resources']
    assert resources == expected_k8s_resources


def test_image_in_app_makes_image_default_unnecessary():
    settings = new_settings()
    app = {"id":"app", "container": {"docker": {"image": "busybox"}}}
    result, _ = app_translator.translate_app(app, settings)
    assert result['spec']['template']['spec']['containers'][0]['image'] == "busybox"


def test_image_should_be_present_somewhere():
    settings = new_settings(image = None)
    app = {"id":"app", "command": "sleep 300"}
    with pytest.raises(app_translator.AdditionalFlagNeeded, match=".*image.*"):
        app_translator.translate_app(app, settings)

def test_translates_args():
    settings = new_settings()
    hello_app = app_translator.load("test/resources/container-args-app.json")[0]
    result, warnings = app_translator.translate_app(hello_app, settings)

    assert(result['kind'] == "Deployment")
    assert(result['metadata']['name'] == "args")
    container = result['spec']['template']['spec']['containers'][0]

    assert(not "command" in container)
    assert(container['args'] == ["args", "passed", "to", "entrypoint"])
