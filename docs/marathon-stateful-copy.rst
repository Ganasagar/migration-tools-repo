Copying Marathon Stateful App Data to the migrated K8s StatefulSets
===================================================================

Copying Marathon stateful app data is driven primarily by a Makefile which is and various assets generated after running
`dcos-migrate migrate`. **Marathon stateful task data is not downloaded** as part of `dcos-migrate backup`.

The Makefile invokes simple scripts which use the ``dcos`` CLI and ``kubectl``, with the following basic approach:

- Sleep the DC/OS application by updating the command to "sleep" (and disabling all health checks). This is needed to
  prevent the state from being modified during download, or any interruptions.
- Download the DC/OS Marathon stateful app data for all instances. The state is stored in
  ``target/download/{idx}/{mount_name}``, where ``{idx}`` is a number starting with 0 and incrementing for each
  instance.
- Sleep the K8s StatefulSet (by patching the container spec with a sleeper command, and disabling probes).
- Upload the state from each Marathon instance to a corresponding StatefulSet pod. If there are 4 pods, then
  ``target/download/0/{mount_name}`` will be uploaded to pod ``{stateful-set-name}-0``
- Resume the K8s StatefulSet by patching the container spec with the original command and and probes.

Pre-requisites
==============

Before copying Marathon stateful app data to the corresponding migrated StatefulSets in Kubernetes, you must:

- Configure your local shell environment for ``kubectl`` and ``dcos cli``
    - The ``dcos cli`` is configured to the source cluster from which you plan to copy Marathon state.
    - ``kubectl`` is configured to the target cluster and namespace
- Generate the ``Makefile``, artifacts, and initial StatefulSet specs by running ``dcos-migrate.py migrate``.
- Tweak the initial StatefulSet specifications as needed for your environment
- Deploy the initial StatefulSet specifications to you K8s cluster
    - Confirm that they launch **successfully**, and that their persistent volume claims are fulfilled.
    - If your cluster does not automatically create volumes to fulfill persistent volume claims, you'll need to fulfill them manually.
- Your shell's ``ulimit`` should be 1024 or higher. ``dcos task download`` will often fail, otherwise.


Initial deploy of stateful sets
===

The StatefulSet written during ``dcos-migrate.py migrate`` contains a sleeper command and omits any probes. This is done
to avoid interruption caused by failing liveliness, or files changing on disk during copy.

The initial sleeper StatefulSet can be deployed by changing to the ``dcos-migrate/migrate/marathon/stateful-copy/``
folder and running ``make init-deploy``.



Running
=======

The entire batch
----------------

Once you've confirmed the prerequisites, and confirmed that the sleeper version of for all StatefulSets (in the initial
generated sleeper form) have deployed successfully, you are ready to copy the state.

You can run the full copy process for all stateful-sets by running the changing to the folder
``dcos-migrate/migrate/marathon/stateful-copy/``, and running:

::

   make copy

This will run ``make copy`` for each of the folders, aborting entirely if one fails. The Makefile remembers which steps
were completed successfully, so if several steps succeed, and then one fails, re-running ``make copy`` won’t cause the
state for the successful apps to be re-copied.

Dealing with errors
--------------------

It's possible that errors occur and interrupt the process. To help understand what succeeded and what didn't, run:

::

   make report


Sometimes, the download can fail and you may wish to continue uploading the state in spite of the failure. For instance,
``dcos task download`` can return an overall result when it encounters a UNIX domain socket, even though all copyable
state did successfully copy. You can force-mark the download as successful.

To do so, change to the subfolder in ``dcos-migrate/migrate/marathon/stateful-copy`` corresponding to the StatefulSet /
instance. For a Marathon app ``/postgres`` and StatefulSet named ``postgres``, this subfolder would be
``dcos-migrate/migrate/marathon/stateful-copy/postgres``. This folder will contain a `Makefile` of its own, along with
some other files, such as ``config.sh``.


Inside of this subfolder, run:

::

   make -t download

You will see the following line in the output if it is successful:

::

   touch target/dcos-downloaded

Change back to the previous folder, and re-run ``make copy`` to continue.
