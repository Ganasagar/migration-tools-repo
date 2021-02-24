from dcos_migrate.system import StorableList, Backup


def create_example_list(dir: str) -> StorableList:
    list = StorableList(str(dir))

    p = "testPlugin"
    b = "foobar"
    d = {"foo": "bar"}
    list.append(Backup(pluginName=p,
                       backupName=b, data=d))

    list.store()
    return list, p, b, d


def test_store(tmpdir):
    dir = tmpdir.mkdir("test")
    list, p, b, d = create_example_list(str(dir))

    assert len(dir.listdir()) == 1
    assert dir.dirpath("test/{}/{}.Backup.json".format(p, b)).check()


def test_load(tmpdir):
    dir = tmpdir.mkdir("test")
    list, p, b, d = create_example_list(str(dir))

    list2 = StorableList(str(dir)).load()

    # we expect different objects
    assert list != list2
    # but the same amount
    assert len(list) == len(list2)
    # and data
    assert list[0].data == list2[0].data
