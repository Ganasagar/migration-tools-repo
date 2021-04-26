# Marathon Stateful Copy

This folder was generated during the `dcos-migrate` `migrate` phase because one or more stateful Marathon apps are present. This folder contains a Makefile and some artifacts to help drive the migrate process.

For detailed description of the state copy process, please see the docs file `marathon-stateful-copy.rst`.

# Useful commands

You'll likely employ a workflow like the following:

```
make help # Show all targets supported by the Makefile, with a description of what each does.

make -j 8 init-deploy # Deploy the initial StatefulSet manifests, allowing 8 to be deployed at a time.

make download # Download state locally from all instances of all stateful apps in DC/OS

make report # Show the current state of the copy workflow. Useful for when an error occurs.

make upload # Upload the downloaded state

make k8s-resume # Switch the k8s statefulset out of sleeper mode

ulimit -n 1024 # needed to overcome an issue that may occur with `dcos task download`

cd {app} && make -t download # force-mark a specific app's download as successful, if it returns a failure for a trivial reason, such as getting tripped up by a UNIX domain socket
```

