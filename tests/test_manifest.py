from kubernetes.client.models import V1beta1CronJob, V1Secret
from dcos_migrate.system import Manifest, with_comment

import textwrap


def test_manifest_deserialize_get_model_name():
    assert "V1Job" == Manifest.genModelName("v1", "Job")
    assert "V1beta1CronJob" == Manifest.genModelName("batch/v1beta1", "CronJob")


def test_manifest_deserialize_multidoc_model():
    with open('tests/examples/multiDocManifest.yaml') as yaml_file:
        m = Manifest(pluginName='metronome', manifestName='test')
        m.deserialize(yaml_file)

        assert len(m) == 2
        assert isinstance(m[0], V1beta1CronJob)
        assert isinstance(m[1], V1Secret)

        assert m[0].metadata.name == "hello-world"


def test_manifest_comments_deserialization():
    @with_comment
    class V1beta1CronJobWithComment(V1beta1CronJob):
        pass

    obj_with_comment = V1beta1CronJobWithComment(api_version='v999', kind='CronJob')
    obj_with_comment.set_comment([
        "Lorem ipsum dolor sit amet,",
        "consectetur\n adipiscing\n  elit",
    ])

    obj_without_comment = V1Secret(api_version='v678', kind='Secret')

    # No stray newlines should be dumped if the comment is empty.
    obj_with_empty_comment = V1beta1CronJobWithComment(api_version='v1234', kind='CronJob')
    obj_with_empty_comment.set_comment([])

    manifest = Manifest(pluginName='foo',
                        manifestName='bar',
                        data=[obj_with_comment, obj_without_comment, obj_with_empty_comment])

    dump = manifest.dumps(None)
    assert dump == textwrap.dedent("""\
        ---
        # Lorem ipsum dolor sit amet,
        # consectetur
        #  adipiscing
        #   elit
        apiVersion: v999
        kind: CronJob

        ---
        apiVersion: v678
        kind: Secret

        ---
        apiVersion: v1234
        kind: CronJob
    """)
