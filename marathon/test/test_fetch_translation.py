import pytest

from ..lib import app_translator

def test_generated_fetch_layout():
    """
    Tests generation of volume and init container for `fetch`.
    NOTE: This neither tests the generation of the fetch script that runs in
    the init container, nor ensures that this script itself actually works!
    """
    settings = app_translator.Settings(
        app_translator.ContainerDefaults(
            image="busybox",
            working_dir="/fetched_artifacts",
        ),
        imported_k8s_secret_name = "dummy"
    )

    fields = {"id": "app", "fetch": [{"uri": "http://foobar.baz/0xdeadbeef"}]}

    result, warnings = app_translator.translate_app(fields, settings)

    template_spec = result['spec']['template']['spec']

    # The volume for fetching artifacts should be an empty dir.
    fetch_volume_name = template_spec['volumes'][0]['name']
    assert template_spec['volumes'] == [{'emptyDir': {}, 'name': fetch_volume_name}]

    # Ensure that the fetch volume will be mounted into the main container as a working dir.
    assert template_spec['containers'][0]['volumeMounts'] ==\
        [{'name': fetch_volume_name, 'mountPath': settings.container_defaults.working_dir}]

    # The fetcher itself should be implemented as a SINGLE init container.
    assert len(template_spec['initContainers']) == 1
    fetch_container = template_spec['initContainers'][0]

    assert fetch_container['volumeMounts'] == \
        [{'name': fetch_volume_name, 'mountPath': fetch_container['workingDir']}]

    # TODO (asekretenko): Write an integration test for the fetch command!
    assert isinstance(fetch_container['command'], list)


def test_fetch_fails_without_working_dir():
    settings = app_translator.Settings(
        app_translator.ContainerDefaults(
            image="busybox",
            working_dir=None,
        ),
        imported_k8s_secret_name = "dummy"
    )

    fields = {"id": "app", "fetch": [{"uri": "http://foobar.baz/0xdeadbeef"}]}

    with pytest.raises(app_translator.AdditionalFlagNeeded, match=r'.*?--container-working-dir.*?'):
        app_translator.translate_app(fields, settings)
