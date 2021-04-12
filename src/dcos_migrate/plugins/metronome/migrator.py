from dcos_migrate.system import Migrator, Manifest
import dcos_migrate.utils as utils
import kubernetes.client.models as K  # type: ignore
import json
import os
import typing as T

EXTRACT_COMMAND = dict([(".zip", "unzip")] + [(ext, "tar -xf")
                                              for ext in [".tgz", ".tar.gz", ".tbz2", ".tar.bz2", ".txz", ".tar.xz"]])


def generate_fetch_command(uri: str, allow_extract: bool, executable: bool) -> str:
    # NOTE: The path separator is always '/', even on Windows.
    _, _, filename = uri.rpartition("/")
    _, ext = os.path.splitext(filename)
    postprocess = ("chmod a+x" if executable else (EXTRACT_COMMAND.get(ext, "") if allow_extract else ""))

    fmt = ('( wget -O "{fn}" "{uri}" && {postprocess} "{fn}" )' if postprocess else '( wget -O "{fn}" "{uri}")')

    return fmt.format(fn=filename, uri=uri, postprocess=postprocess)


class MetronomeMigrator(Migrator):
    """docstring for SecretsMigrator."""
    def __init__(
        self,
        defaultImage: str = "alpine:latest",
        workingDir: str = "/work",
        **kw: T.Any,
    ):
        super(MetronomeMigrator, self).__init__(**kw)

        self.manifest: "Manifest"
        self.image = defaultImage
        self.workingDir = workingDir
        self.jobSecret: T.Any = None
        self._warnings: T.Dict[str, str] = dict()
        self.translate = {
            "id": self.initCronJob,
            # id comes first to init our manifest object...
            "run.secrets.*": self.handleSecret,
            "dependencies|run.docker.parameters": self.noEquivalent,
            "description": self.handleDescription,
            "run.env": self.handleEnv,
            "labels.*": self.handleLabels,
            "run.args": self.handleRunArgs,
            "run.artifacts": self.handleArtifacts,
            "run.cmd": self.handleCmd,
            "run.cpus": self.handleLimitsCPUs,
            "run.disk": self.handleLimitsDisk,
            "run.docker.forcePullImage": self.handleForcePull,
            "run.docker.image": self.handleImage,
            "run.docker.privileged": self.handlePrivileged,
            "run.gpus": self.handleLimitsGPUs,
            "run.maxLaunchDelay": self.handleMaxLaunchDelay,
            "run.mem": self.handleLimitsMem,
            "run.networks": self.handleNetworks,
            "run.placement.constraints": self.handlePlacementConstraints,
            "run.restart.activeDeadlineSeconds": self.handleActiveDeadlineSeconds,
            "run.restart.policy": self.handleRestartPolicy,
            "run.taskKillGracePeriodSeconds": self.handleTaskKillGracePeriod,
            "run.ucr.image": self.handleUCR,
            "run.user": self.handleUser,
            "run.volumes": self.handleVolumes,
            "schedules[0]": self.handleSchedule,
        }

    @property
    def cronJob(self) -> "K.V1beta1CronJob":
        return self.manifest[0]

    @property
    def jobSpec(self) -> "K.V1JobSpec":
        return self.cronJob.spec.job_template.spec

    @property
    def container(self) -> "K.V1Container":
        return self.jobSpec.template.spec.containers[0]

    def warn(self, path: str, msg: str) -> None:
        self._warnings[path] = msg

    def initCronJob(self, key: str, value: str, full_path: str) -> None:
        name = self.dnsify(value)
        metadata = K.V1ObjectMeta(name=name)
        assert self.manifest_list
        clusterMeta = self.manifest_list.clusterMeta()
        if clusterMeta:
            metadata.annotations = clusterMeta.annotations

        # intentionally written this way so one can easily scan down paths
        container1 = K.V1Container(
            name="job",
            resources=K.V1ResourceRequirements(limits={}, requests={}),
        )
        self.manifest = Manifest(
            data=[
                K.V1beta1CronJob(
                    metadata=metadata,
                    kind="CronJob",
                    api_version="batch/v1beta1",
                    spec=K.V1beta1CronJobSpec(
                        schedule="* * * * *",
                        suspend=True,
                        job_template=K.V1beta1JobTemplateSpec(spec=K.V1JobSpec(template=K.V1PodTemplateSpec(
                            spec=K.V1PodSpec(containers=[container1])))),
                    ),
                )
            ],
            pluginName="metronome",
            manifestName=name,
        )

    def handleActiveDeadlineSeconds(self, key: str, value: str, full_path: str) -> None:
        self.warn(
            full_path,
            f'DKP has no equivalent for "run.restart.activeDeadlineSeconds", dropping: {value}',
        )

    def handleArtifacts(self, key: str, value: T.List[T.Any], full_path: str) -> None:
        if len(value) < 1:
            return

        def iter_command() -> T.Generator[str, None, None]:
            yield "set -x"
            yield "set -e"
            yield "FETCH_PID_ARRAY=()"
            for fetch in value:
                fetch = fetch.copy()
                uri = fetch.pop("uri")
                cache = fetch.pop("cache", False)
                extract = fetch.pop("extract", True)
                executable = fetch.pop("executable", False)
                if fetch:
                    self.warn(full_path, f'Unknown fields in "fetch": {json.dumps(fetch)}')
                if cache:
                    self.warn(
                        full_path,
                        f'`cache=true` requested for fetching "{uri}" has been ignored',
                    )
                if uri.startswith("file://"):
                    self.warn(full_path, f"Fetching a local file {uri} is not portable")
                yield generate_fetch_command(uri, extract, executable) + ' & FETCH_PID_ARRAY+=("$!")'
            yield "for pid in ${FETCH_PID_ARRAY[@]}; do wait $pid || exit $?; done"

        self.container.volume_mounts = [{
            "name": "fetch-artifacts",
            "mountPath": self.workingDir,
        }]
        self.jobSpec.template.spec.init_containers = [{
            "name":
            "fetch",
            "image":
            "bash:5.0",
            "command": ["bash", "-c", "\n".join(iter_command())],
            "volumeMounts": [{
                "name": "fetch-artifacts",
                "mountPath": "/fetch-artifacts"
            }],
            "workingDir":
            "/fetch_artifacts",
        }]
        self.jobSpec.template.spec.volumes = [{"name": "fetch-artifacts", "emptyDir": {}}]

    def handleCmd(self, key: str, value: str, full_path: str) -> None:
        if value and value != "":
            self.container.command = ["/bin/sh", "-c", value]

    def handleDescription(self, key: str, value: str, full_path: str) -> None:
        self.cronJob.metadata.annotations["migration.dcos.d2iq.com/description"] = value

    def handleSecret(self, key: str, value: T.Dict[str, str], full_path: str) -> None:
        if not self.jobSecret:
            assert self.object
            name = self.dnsify("jobsecret." + str(self.object.get("id", "")))
            metadata = K.V1ObjectMeta(name=name)
            assert self.manifest_list
            clusterMeta = self.manifest_list.clusterMeta()
            if clusterMeta:
                metadata.annotations = clusterMeta.annotations
            self.jobSecret = K.V1Secret(metadata=metadata, data={})
            self.jobSecret.api_version = 'v1'
            self.jobSecret.kind = 'Secret'
            self.manifest.append(self.jobSecret)

        sourceSecretName = value.get("source", "")

        if not sourceSecretName:
            # logging.critical("{}.source missing", full_path)
            return

        source_key = utils.dnsify(sourceSecretName)
        assert self.manifest_list
        sourceSecret = self.manifest_list.manifest(pluginName='secret', manifestName=source_key)
        if not sourceSecret:
            # logging.warning("secret {} missing", source_key)
            self.jobSecret.data[key] = "{} not found".format(source_key)
            return

        [v] = sourceSecret[0].data.values()

        self.jobSecret.data[key] = v

    def handleEnv(self, key: str, value: T.Dict[str, T.Any], full_path: str) -> None:
        env = []
        for k, v in value.items():
            if "secret" in v:
                if not self.jobSecret:
                    # logging.critical("No secret found")
                    return

                keyRef = self.jobSecret.metadata.name

                # TODO: find ref from secrets metadata
                key_selector = K.V1SecretKeySelector(key=v["secret"], name=keyRef)
                env_var_src = K.V1EnvVarSource(secret_key_ref=key_selector)
                env.append(K.V1EnvVar(name=k, value_from=env_var_src))
            else:
                env.append(K.V1EnvVar(name=k, value=v))

        self.container.env = env

    def handleForcePull(self, key: str, value: str, full_path: str) -> None:
        self.container.image_pull_policy = "Always" if value else "IfNotPresent"

    def handleImage(self, key: str, value: str, full_path: str) -> None:
        self.container.image = value

    def handleLabels(self, key: str, value: str, full_path: str) -> None:
        k = f"migration.dcos.d2iq.com/label/{key}"
        self.cronJob.metadata.annotations[k] = value

    def handleLimitsCPUs(self, key: str, value: float, full_path: str) -> None:
        self.container.resources.limits.update({"cpu": value})

    def handleLimitsDisk(self, key: str, value: float, full_path: str) -> None:
        if value == 0:
            return
        self.container.resources.limits["ephemeral-storage"] = str(value) + "Mi"

    def handleLimitsGPUs(self, key: str, value: float, full_path: str) -> None:
        self.container.resources.requests["nvidia.com/gpu"] = value
        self.container.resources.limits["nvidia.com/gpu"] = value

    def handleLimitsMem(self, key: str, value: float, full_path: str) -> None:
        self.container.resources.limits["memory"] = str(value) + "Mi"

    def handleMaxLaunchDelay(self, key: str, value: int, full_path: str) -> None:
        if not value == 3600:
            self.warn(full_path, "maxLaunchDelay is not available in DKP")

    def handleNetworks(self, key: str, value: T.Any, full_path: str) -> None:
        if value != []:
            self.warn(full_path, "conversion of .run.networks is not yet implemented.")

    def handlePlacementConstraints(self, key: str, value: T.Any, full_path: str) -> None:
        if value != []:
            self.warn(
                full_path,
                "conversion of .run.placement.constraints not implemented.",
            )

    def handlePrivileged(self, key: str, value: bool, full_path: str) -> None:
        self.container.securityContext = K.V1PodSecurityContext(dict(privileged=value))

    def handleRestartPolicy(self, key: str, value: str, full_path: str) -> None:
        # A CronJob cannot use the implicit default restartPolicy of `Always`,
        # so we always need to set this.  The valid values for a CronJob are
        # `OnFailure` and `Never`.  Unless we come up with a good translation
        # from Metronome's `activeDeadlineSeconds` to K8s `backoffLimit` the
        # most reasonable value is `Never`.
        if value.upper() != "NEVER":
            self.warn(full_path, f"Metronome restart policy '{value}' was dropped.")
        self.jobSpec.template.spec.restart_policy = 'Never'

    def handleRunArgs(self, key: str, value: T.List[str], full_path: str) -> None:
        self.container.args = value

    def handleSchedule(self, key: str, value: T.Any, full_path: str) -> None:
        if "concurrencyPolicy" in value:
            self.cronJob.spec.concurrencyPolicy = value["concurrencyPolicy"].title()
        if "cron" in value:
            self.cronJob.spec.schedule = value["cron"]
        if "enabled" in value:
            self.cronJob.spec.suspend = not value["enabled"]
        if "startingDeadlineSeconds" in value:
            self.cronJob.spec.startingDeadlineSeconds = value["startingDeadlineSeconds"]
        if "timeZone" in value:
            v = value["timeZone"]
            if not ("UTC" == v):
                self.warn(
                    full_path,
                    f'You might need to edit the cron expression (spec.schedule) to account for an update from "{value}" to your target cluster\'s timezone.',
                )

    def handleTaskKillGracePeriod(self, key: str, value: int, full_path: str) -> None:
        self.jobSpec.terminationGracePeriodSeconds = value

    def handleUCR(self, key: str, value: T.Dict[str, T.Any], full_path: str) -> None:
        # we're converting things here if the "kind" is "docker". we always warn about that.
        if value.get("kind") != "docker":
            self.warn(
                full_path,
                f"Can't migrate '{full_path}'. Please convert and add your UCR configuration to the resulting yaml manually.",
            )
            return

        self.warn(
            full_path,
            "Converting UCR configuration with .kind 'docker'. Please double check the result.",
        )

        self.handleImage("image", value["id"], full_path + ".id")
        if value.get("forcePull") is not None:
            self.handleForcePull("forcePull", value["forcePull"], full_path + ".forcePull")

        if value.get("privileged") is not None:
            self.handlePrivileged("privileged", value["privileged"], full_path + ".privileged")

    def handleUser(self, key: str, value: str, full_path: str) -> None:
        self.warn(
            full_path,
            f'Found "run.user": "{value}". You might need to set "spec.template.spec.containers[].securityContext.runAsUser" manually, as we can\'t infer a mapping to the according uid on the target node.',
        )
        pass

    def handleVolumes(self, key: str, value: T.Any, full_path: str) -> None:
        # BEWARE WHILE IMPLEMENTING: "artifacts" might have set some volumes already
        self.warn(full_path, "TODO: conversion of .run.volumes is not yet implemented.")
