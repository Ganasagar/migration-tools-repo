from dcos_migrate.plugins.plugin_manager import PluginManager
from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.system import ArgParse, Arg

import pytest


def test_auto_discovery():
    pm = PluginManager()

    assert "cluster" in pm.plugins.keys()
    assert "marathon" in pm.plugins.keys()
    assert "secret" in pm.plugins.keys()


@pytest.fixture
def plugin_manager():
    class Test1Plugin(MigratePlugin):
        """docstring for ClusterPlugin."""
        plugin_name = "test1"
        # No depends wanna run first

        def __init__(self):
            super(Test1Plugin, self).__init__()

            self._config_options = [Arg(
                "option1", plugin_name=self.plugin_name
            )]

    class Test2Plugin(MigratePlugin):
        """docstring for ClusterPlugin."""
        plugin_name = "test2"
        migrate_depends = ['test1']

        def __init__(self):
            super(Test2Plugin, self).__init__()

            self._config_options = [Arg(
                "option1", plugin_name=self.plugin_name
            )]

    class Test3Plugin(MigratePlugin):
        """docstring for ClusterPlugin."""
        plugin_name = "test3"
        migrate_depends = ['test1', 'test2']

        def __init__(self):
            super(Test3Plugin, self).__init__()

    return PluginManager(plugins={
        'test1': Test1Plugin(),
        'test2': Test2Plugin(),
        'test3': Test3Plugin()
    })


def test_dependencies(plugin_manager):
    assert len(plugin_manager.plugins) == 3
    assert len(plugin_manager.migrate) == 3
    assert plugin_manager.migrate_batch == [[plugin_manager.plugins['test1']],
                                            [plugin_manager.plugins['test2']],
                                            [plugin_manager.plugins['test3']]
                                            ]


def test_plugin_argparse(plugin_manager):
    assert len(plugin_manager.config_options) == 2

    ap = ArgParse(plugin_manager.config_options)

    cli = [
        "--test1-option1", "foo",
        "--test2-option1", "bar",
    ]

    options = ap.parse_args(cli)
    assert options == {
        "test1": {
            "option1": "foo"
        },
        "test2": {
            "option1": "bar"
        }
    }

    plugin_manager.config = options

    assert plugin_manager.plugins['test1'].plugin_config == {"option1": "foo"}
    assert plugin_manager.plugins['test2'].plugin_config == {"option1": "bar"}
