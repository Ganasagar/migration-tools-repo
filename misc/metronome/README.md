# Metronome Migration Tool

This guide will walk you through the migration commands in order to migrate Metronome jobs to Kubernetes resources.

## Prerequisites

- `python3` with `pyyaml`.
- DC/OS-CLI in order to download Job Specs
- Kubernetes CLI `kubectl` setup to talk to a Kubernetes cluster

## Commands


Please have a look at `./migrate.py --help` and `./migrate.py translate --help`.

A typical workflow might look like this:

### Authenticate with your DC/OS Cluster

```
➜ dcos cluster setup <CLUSTER_ID>
```

### Download all job specs

`./migrate.py download` will download all job specs present on that cluster to `./metronome-jobs/<JOB_ID>.json`.

### Translate jobs:

`./migrate.py translate <PATH>` will convert your job to a Kubernetes resource. That
will be a `CronJob` in case a schedule is present and a `Job` otherwise. It
might show warnings on `stderr` along the way:

```
./metronome-jobs/job1.json > job1.yaml
➜ ./migrate.py translate ./metronome-jobs/job1.json > job1.yaml
[WARN] Converting UCR configuration as .kind is 'docker'. Please check whether UCR is required for your use case.
```

#### Translate all

```
mkdir -p dkp-jobs
for f in ./metronome-jobs/*.json
do
 echo "=== Processing $f ==="
 ./migrate.py translate $f > "dkp-jobs/$(basename "$f" .json).yaml"
done
```

your main call might provide a default image to fall back to as well as a secret reference and a working-dir in case your job makes use of artifacts:

```
 ./migrate.py translate --image busybox --imported-k8s-secret-name my-secret --working-dir /app $f > "dkp-jobs/$(basename "$f" .json).yaml"
```

you might also want to specify `--force-cronjob` to always produce a `CronJob`, as that's closer to a DC/OS job because it can be ran more than once.


### Evaluate the results

You'll now have `yaml** files and potentially some warnings that came up during translation.
Please have a look at every single warning. Additionally here are more things to consider:

#### The following settings are not translated if they're set to default values

Metronome adds default values to every Job specification. In order to reduce the noise in the warnings for options that have no equivalent in DKP, we'll ignore the following options when they are set to their default values. Please make sure that this is sensible in the customers environment.

* `maxLaunchDelay (3600)` - The number of seconds until the job needs to be running. If this deadline is reached without successfully running the job, the job is aborted. Kubernetes has no equivalent for this.

* `schedule.timeZone ("UTC")` - Kubernetes has no equivalent on `CronJob`s. Instead `CronJob`-schedules are based on the timezone of the `kube-controller-manager`. Make sure to update the resulting yaml's cron-schedule if "UTC" been chosen deliberately and the `kube-controller-manager` uses a different time zone. In case you have a use case that requires converting a lot of those, please reach out to engineering.
* `.run.cpu (0)` TODO maybe we just add them in any case.
* `.run.disk (0)` TODO
* `.run.gpus (0)`  TODO
* `.run.mem (0)`  TODO

#### The following settings are dropped

* `dependencies` - there's no direct equivalent in Kubernetes and we don't expect any customer to use those yet. If you have a use case, please reach out to engineering.
* `run.docker.parameters` - there's no equivalent in Kubernetes.
* `run.restart.activeDeadlineSeconds` - "If the job fails, how long should we try to restart the job". There's no equivalent in Kubernetes. BEWARE: `Pod`'s `.spec.activeDeadlineSeconds` has the same name but very different semantics!
* `run.restart.policy` when `OnFailure` - Metronome's `OnFailure` will have a look at `run.restart.activeDeadlineSeconds` and try to restart the job for that amount of seconds. In Kubernetes you might want to set a `spec.backoffLimit` to set the amount of **times** it shall try to restart the Job. This is 6 by default.

#### Side Notes

* `artifacts` - are now pulled in via `initContainers` before starting the Job's Pod.
* `run.ucr` - we convert this in case `kind` is set to `docker`. Else they're ignored and you might need to set `resources.image`, `resources.imagePullPolicy`, and/or `securityContext.privileged` manually in the resulting yaml. You'll get an warning whenever `UCR` configuration is present.
* `run.secrets` - you'll need to create a k8s-secret separately. there's a script for that in this repo. you'll need to specify a `--imported-k8s-secret-name` if the job you convert makes use of secrets. in case you want to reference multiple k8s-secrets, you currently need to manually correct the data in the resulting yaml. we plan on supporting that in the future though.

### Deploy the resulting yamls onto a Kubernetes cluster.

TODO
