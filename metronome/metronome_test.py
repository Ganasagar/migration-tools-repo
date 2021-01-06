from migrate import translate
import json
import os


def snapshot_test(snapshot, fn, source, target):
    snapshot.snapshot_dir = "snapshots"
    with open(f"{os.path.dirname(__file__)}/../snapshots/{source}") as f:
        snapshot.assert_match(fn(json.load(f)), target)


###############################################################################
#                                    TESTS                                    #
###############################################################################
def test_job(snapshot):
    snapshot_test(snapshot, translate, "test-job.json", "test-job.yaml")


def test_cronjob(snapshot):
    snapshot_test(snapshot, translate, "test-cronjob.json", "test-cronjob.yaml")


def test_force_cronjob(snapshot):
    snapshot_test(
        snapshot,
        lambda json: translate(json, {"force_cronjob": True}),
        "test-job.json",
        "test-force-cronjob.yaml",
    )
