import argparse
from dcos_migrate.system.argparse import Arg, ArgParse, BoolArg, DictArg


def test_arg():
    a = Arg("foo", plugin_name="testplugin")

    assert a.arg == "testplugin-foo"
    assert a.arg_name == "--testplugin-foo"

    parser = argparse.ArgumentParser()
    a.add_argument(parser)
    pargs = parser.parse_args(["--testplugin-foo", "bar"])
    res = a.get_result(pargs)

    assert res == "bar"


def test_argparse_parse():
    args = [
        Arg("image", plugin_name="testplugin"),
        DictArg("secretoverwrites", plugin_name="testplugin"),
        BoolArg("insecure", plugin_name="testplugin"),
        BoolArg("testoption")
    ]
    cliargs = ["--testplugin-image", "image:foo",
               "--testplugin-secretoverwrites", "dcos/secret1=k8s.secret1", "dcos/secret2=k8s.secret2",
               "--testplugin-insecure",
               "--testoption",
               ]

    options = {
        'global': {
            'testoption': True
        },
        'testplugin': {
            'image': "image:foo",
            "secretoverwrites": {
                "dcos/secret1": "k8s.secret1",
                "dcos/secret2": "k8s.secret2"
            },
            "insecure": True
        }
    }

    p = ArgParse(args)

    parsed = p.parse_args(cliargs)

    assert parsed == options
