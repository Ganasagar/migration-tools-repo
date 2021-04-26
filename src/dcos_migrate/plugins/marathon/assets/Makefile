SHELL=/bin/bash -o pipefail -e
ALL_APPS=$(shell find * -name config.sh -exec dirname {} \; | sort)

SUB_TARGETS=download upload dcos-resume k8s-resume k8s-sleep dcos-sleep report copy init-deploy

.PHONY=$(SUB_TARGETS) $(foreach A,$(ALL_APPS),$(foreach T,$(SUB_TARGETS),$(A)/$(T)))

define help
endef

report: ## Report the copy status for all StatefulSets
	@bin/report $(ALL_APPS)

%/target/init-deployed %/target/k8s-resumed %/target/k8s-slept %/target/dcos-resumed %/target/dcos-slept %/target/copied %/target/dcos-downloaded %/target/k8s-uploaded:
	cd $(*F); make target/$(@F) 2>&1 | ../bin/prefixed $(*F)


download: $(foreach A,$(ALL_APPS),$(A)/target/dcos-downloaded) ## Download all data for all resident Marathon apps; sleep the DC/OS app, first.
copy: $(foreach A,$(ALL_APPS),$(A)/target/copied) ## Run the full state copy, sleeping the Marathon app and K8S StatefulSet
upload: $(foreach A,$(ALL_APPS),$(A)/target/k8s-uploaded) ## Upload all downloaded data to all K8S StatefulSets via kubectl cp; sleep each K8s StatefulSet, first.
dcos-sleep: $(foreach A,$(ALL_APPS),$(A)/target/dcos-slept) ## Ensure that all DC/OS apps are slept.
dcos-resume: $(foreach A,$(ALL_APPS),$(A)/target/dcos-resumed) ## Ensure that all DC/OS apps are resumed.
k8s-sleep: $(foreach A,$(ALL_APPS),$(A)/target/k8s-slept) ## Sleep all StatefulSet
k8s-resume: $(foreach A,$(ALL_APPS),$(A)/target/k8s-resumed) ## Resume all K8s StatefulSets
init-deploy: $(foreach A,$(ALL_APPS),$(A)/target/init-deployed) ## Deploy the initial migrated K8s StatefulSet


# https://www.client9.com/self-documenting-makefiles/
help:
	@awk -F ':|##' '/^[^\t].+?:.*?##/ {\
	printf "\033[36m%-30s\033[0m %s\n", $$1, $$NF \
	        }' Makefile
.DEFAULT_GOAL=help
