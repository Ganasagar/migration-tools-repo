import pytest

from dcos_migrate.plugins.marathon import app_translator
from dcos_migrate.plugins.marathon.app_secrets import TrackingAppSecretMapping

from .common import DummyAppSecretMapping
from typing import Sequence


def new_settings(image: str = "busybox"):
    return app_translator.Settings(
        app_translator.ContainerDefaults(
            image=image,
            working_dir=".",
        ),
        app_secret_mapping=DummyAppSecretMapping(),
    )


def test_happy_path_stateful():
    settings = new_settings()
    hello_app = app_translator.load("tests/test_marathon/test_app_transtalor/resources/stateful-app.json")[0]

    translated = app_translator.translate_app(hello_app, settings)

    assert (translated.deployment['kind'] == 'StatefulSet')
    [mount] = translated.deployment['spec']['template']['spec']['containers'][0]['volumeMounts']
    [vc_template] = translated.deployment['spec']['volumeClaimTemplates']
    assert mount['name'] == "data"
    assert vc_template['spec']['accessModes'] == ['ReadWriteOnce']
    assert vc_template['spec']['resources']['requests']['storage'] == '512Mi'
    assert not 'strategy' in translated.deployment['spec'].keys()
