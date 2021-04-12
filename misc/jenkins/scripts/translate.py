import os
import xml.etree.ElementTree as ET
import logging as log
import xml.dom.minidom

from string import Template
from xml.sax.saxutils import escape

# Kubernetes Cloud templates - EDIT ONLY IF YOU KNOW WHAT YOU ARE DOING!
KUBERNETES_CLOUD_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.KubernetesCloud plugin="kubernetes@1.24.1">
    <name>$NAME</name>
    <defaultsProviderTemplate></defaultsProviderTemplate>
    <templates>
        $POD_TEMPLATES
    </templates>
    <serverUrl></serverUrl>
    <skipTlsVerify>false</skipTlsVerify>
    <addMasterProxyEnvVars>false</addMasterProxyEnvVars>
    <capOnlyOnAlivePods>false</capOnlyOnAlivePods>
    <webSocket>false</webSocket>
    <directConnection>false</directConnection>
    <jenkinsUrl>$JENKINS_URL</jenkinsUrl>
    <jenkinsTunnel>$JENKINS_TUNNEL</jenkinsTunnel>
    <containerCap>10</containerCap>
    <retentionTimeout>5</retentionTimeout>
    <connectTimeout>5</connectTimeout>
    <readTimeout>15</readTimeout>
    <podLabels/>
    <usageRestricted>false</usageRestricted>
    <maxRequestsPerHost>32</maxRequestsPerHost>
    <waitForPodSec>600</waitForPodSec>
    <podRetention class="org.csanchez.jenkins.plugins.kubernetes.pod.retention.Never"/>
</org.csanchez.jenkins.plugins.kubernetes.KubernetesCloud>
"""

KUBERNETES_POD_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.PodTemplate>
    <inheritFrom></inheritFrom>
    <name>$label</name>
    <namespace></namespace>
    <privileged>false</privileged>
    <capOnlyOnAlivePods>false</capOnlyOnAlivePods>
    <alwaysPullImage>false</alwaysPullImage>
    <instanceCap>$INSTANCE_CAP</instanceCap>
    <slaveConnectTimeout>100</slaveConnectTimeout>
    <idleMinutes>0</idleMinutes>
    <activeDeadlineSeconds>0</activeDeadlineSeconds>
    <label>$label</label>
    <nodeSelector></nodeSelector>
    <nodeUsageMode>$nodeUsageMode</nodeUsageMode>
    <hostNetwork>$hostNetwork</hostNetwork>
    <workspaceVolume class="org.csanchez.jenkins.plugins.kubernetes.volumes.workspace.EmptyDirWorkspaceVolume">
        <memory>false</memory>
    </workspaceVolume>
    <volumes>$VOLUMES</volumes>
    <containers>$CONTAINERS</containers>
    <envVars/>
    <annotations/>
    <imagePullSecrets/>
    <nodeProperties/>
    <yamlMergeStrategy class="org.csanchez.jenkins.plugins.kubernetes.pod.yaml.Overrides"/>
    <showRawYaml>true</showRawYaml>
    <podRetention class="org.csanchez.jenkins.plugins.kubernetes.pod.retention.Default"/>
</org.csanchez.jenkins.plugins.kubernetes.PodTemplate>
"""

KUBERNETES_CONTAINER_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.ContainerTemplate>
    <name>$CONTAINER_NAME</name>
    <image>$image</image>
    <privileged>false</privileged>
    <alwaysPullImage>$alwaysPullImage</alwaysPullImage>
    <workingDir></workingDir>
    <command>$command</command>
    <args></args>
    <ttyEnabled>false</ttyEnabled>
    <resourceRequestCpu></resourceRequestCpu>
    <resourceRequestMemory></resourceRequestMemory>
    <resourceLimitCpu></resourceLimitCpu>
    <resourceLimitMemory></resourceLimitMemory>
    <envVars>$envVars</envVars>
    <ports>$ports</ports>
    <livenessProbe>
        <execArgs></execArgs>
        <timeoutSeconds>0</timeoutSeconds>
        <initialDelaySeconds>0</initialDelaySeconds>
        <failureThreshold>0</failureThreshold>
        <periodSeconds>0</periodSeconds>
        <successThreshold>0</successThreshold>
    </livenessProbe>
</org.csanchez.jenkins.plugins.kubernetes.ContainerTemplate>
"""

CONFIGMAP_VOLUME_MOUNT_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.volumes.ConfigMapVolume>
    <mountPath>$mountPath</mountPath>
    <configMapName>$configMapName</configMapName>
</org.csanchez.jenkins.plugins.kubernetes.volumes.ConfigMapVolume>
"""

HOSTPATH_VOLUME_MOUNT_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.volumes.HostPathVolume>
    <mountPath>$mountPath</mountPath>
    <hostPath>$hostPath</hostPath>
</org.csanchez.jenkins.plugins.kubernetes.volumes.HostPathVolume>
"""

PORT_MAPPING = """
<org.csanchez.jenkins.plugins.kubernetes.PortMapping>
    <name>$name</name>
    <containerPort>$containerPort</containerPort>
    <hostPort>$hostPort</hostPort>
</org.csanchez.jenkins.plugins.kubernetes.PortMapping>
"""

ENV_VARS = """
<org.csanchez.jenkins.plugins.kubernetes.model.KeyValueEnvVar>
    <key>$key</key>
    <value>$value</value>
</org.csanchez.jenkins.plugins.kubernetes.model.KeyValueEnvVar>
"""


def plugin100Transform(cloud) -> str:
    # slaveInfos in Mesos to PodTemplate in K8S
    MESOS_100_TO_K8S_POD = {
        "labelString": "label",
        "mode": "nodeUsageMode",
        "idleTerminationMinutes": "idleMinutes",
    }

    # ContainerInfo in Mesos to ContainerTemplate in K8S
    MESOS_100_TO_K8S_CONTAINER = {
        "dockerImage": "image",
        "dockerForcePullImage": "alwaysPullImage",
        "dockerPrivilegedMode": "privileged",
    }

    # Things that exist at mesos "pod level" (children of MesosSlaveInfo) that map to k8s container template
    MESOS_100_POD_TO_KUBERNETES_CONTAINER = {
        # "remoteFSRoot": "workingDir", # TODO : workingDir is mounted as emptyDir in k8s so this isn't working
    }

    NAME = cloud.find("name").text

    if NAME is None or len(NAME) == 0:
        log.warning("Unnamed cloud found, skipping..")
        return

    # Iterate over slaveInfos
    slave_infos_str = "slaveInfos"
    slaveInfos = cloud.find(slave_infos_str)
    if len(slaveInfos) == 0:
        log.warning(f"No {slave_infos_str} found for cloud {NAME}, nothing to transform.")
        return

    pod_templates = []
    for index in range(len(slaveInfos)):
        slave_info = slaveInfos[index]
        msg = f'"{NAME}" cloud at slaveInfo index "{index}"'
        label = slave_info.find("labelString")
        if label is not None and len(label.text) > 0:
            msg = f'{msg} with label "{label.text}"'
        else:
            msg = f'{msg} with empty label'
        log.info("Processing {}".format(msg))

        # There MUST be containerInfo in Agent spec. If not, it points to UCR runtime and we can't transform
        containerInfo = slave_info.find("containerInfo")
        container_template_subs = {}
        if containerInfo is None:
            log.info(f'No "containerInfo" found in {msg}. (probably the default node?). skipping..')
            continue

        pod_template_subs = {}
        for mesos_field_name, k8s_field_name in MESOS_100_TO_K8S_POD.items():
            field = slave_info.find(mesos_field_name)
            k8s_field_value = ""
            if field is not None:
                k8s_field_value = field.text
            if len(k8s_field_value) == 0:
                log.warning(f'Key "{mesos_field_name}" not found in {msg}. Defaulting to empty string.')
            pod_template_subs[k8s_field_name] = k8s_field_value

        for mesos_field_name, k8s_field_name in MESOS_100_TO_K8S_CONTAINER.items():
            field = containerInfo.find(f"./{mesos_field_name}")
            k8s_field_value = ""
            if field is not None:
                k8s_field_value = field.text
            if len(k8s_field_value) == 0:
                log.warning(f"Unable to substitute {k8s_field_name} in cloud named {NAME}")
                continue
            container_template_subs[k8s_field_name] = k8s_field_value

        for mesos_field_name, k8s_field_name in MESOS_100_POD_TO_KUBERNETES_CONTAINER.items():
            field = slave_info.find(mesos_field_name)
            k8s_field_value = ""
            if field is not None:
                k8s_field_value = field.text
            if len(k8s_field_value) == 0:
                log.warning(f'Key "{mesos_field_name}" not found in {msg}. Defaulting to empty string.')
            container_template_subs[k8s_field_name] = k8s_field_value

        # If the "isDind" AND "useCustomDockerCommandShell" are set to "true" in containerInfo,
        # check if "customDockerCommandShell" is equal to "wrapper.sh" and overwrite as needed
        container_template_subs["command"] = escape(JENKINS_AGENT_ENTRYPOINT)
        isDind = containerInfo.find("isDind")
        useCustomDockerCommandShell = containerInfo.find("useCustomDockerCommandShell")
        customDockerCommandShell = containerInfo.find("customDockerCommandShell")
        if isDind is not None and useCustomDockerCommandShell is not None and customDockerCommandShell is not None:
            if bool(isDind.text) and bool(useCustomDockerCommandShell.text):
                if customDockerCommandShell.text == "wrapper.sh":
                    container_template_subs["command"] = escape(f"wrapper.sh {JENKINS_AGENT_ENTRYPOINT}")

        # Loss of information for "additionalURIs" at slaveInfo level and "parameters" at "containerInfo" level
        for item in ["additonalURIs"]:
            if slave_info.find(item) is not None:
                log.warning(f"Dropping {item} found in {msg}")
        for item in ["parameters"]:
            if containerInfo.find(item) is not None:
                log.warning(f"Dropping {item} found in {msg}")

        # Map network type. HOST networking is bool variable at pod level.
        # If Bridge is selected, inject the port mappings at container level.
        networking = containerInfo.find("./networking")
        pod_template_subs["hostNetwork"] = "false"  # default value gets overridden below
        container_template_subs["ports"] = ""  # default value gets overridden below
        if networking is None:
            log.info('Element "networking" not found in "containerInfo"')
        else:
            networkType = networking.text
            container_template_subs["networking"] = networking
            if networkType == "BRIDGE":
                mesos_port_mappings = containerInfo.find(f"./portMappings")
                if mesos_port_mappings is None or len(mesos_port_mappings) == 0:
                    log.info("No portMappings found in BRIDGE mode")
                else:
                    k8s_port_mappings = []
                    for port_mapping in mesos_port_mappings:
                        containerPort = port_mapping.find("./containerPort").text
                        hostPort = port_mapping.find("./hostPort").text
                        protocol = port_mapping.find("./protocol").text
                        # use name as protocol (udp OR tcp)
                        k8s_port_mappings.append(
                            Template(PORT_MAPPING).substitute(containerPort=containerPort,
                                                              hostPort=hostPort,
                                                              name=protocol))
                    container_template_subs["ports"] = "".join(k8s_port_mappings)
            elif networkType == "HOST":
                pod_template_subs["hostNetwork"] = "true"
            elif networkType == "USER":
                log.warning('Element "networking" of type "USER" not supported in k8s')
            else:
                log.warning("Invalid value for networking : {}".format(networkType))

        # Inject the volume mounts. Mandatory ConfigMap volume mount followed by 0 or more mounts from mesos plugin configuration
        volumes = [
            Template(CONFIGMAP_VOLUME_MOUNT_TEMPLATE).substitute(mountPath="/var/configmaps",
                                                                 configMapName="jenkins-agent-3-35-5")
        ]
        mesos_volumes = containerInfo.find("volumes")
        if mesos_volumes is not None and len(mesos_volumes) > 0:
            for v in mesos_volumes:
                hostPath = v.find("./hostPath")
                containerPath = v.find("./containerPath")
                readOnly = v.find("./readOnly")
                if readOnly == "true":
                    log.warning("ignoring readOnly flag for volume mount {}:{}".format(hostPath, containerPath))
                volumes.append(
                    Template(HOSTPATH_VOLUME_MOUNT_TEMPLATE).substitute(mountPath=containerPath, hostPath=hostPath))
        pod_template_subs["VOLUMES"] = "".join(volumes)

        # Override the jnlp container that would usually be injected by kubernetes plug in
        container_template_subs["CONTAINER_NAME"] = "jnlp"

        # Add jnlpArgs and jvmArgs as environment variables to entrypoint command
        jnlpArgs = slave_info.find("./jnlpArgs")
        jvmArgs = slave_info.find("./jvmArgs")
        envVars = []
        if jnlpArgs:
            envVars.append(Template(ENV_VARS).substitute(key="JNLP_PROTOCOL_OPTS", value=jnlpArgs.text))
        if jvmArgs:
            envVars.append(Template(ENV_VARS).substitute(key="JAVA_OPTS", value=jvmArgs.text))
        # TODO : translate env vars from mesos config
        container_template_subs["envVars"] = "".join(envVars)

        # Mesos config allows only ONE container
        pod_template_subs["CONTAINERS"] = Template(KUBERNETES_CONTAINER_TEMPLATE).substitute(container_template_subs)
        pod_template_subs["INSTANCE_CAP"] = 100  # TODO
        pod_templates.append(Template(KUBERNETES_POD_TEMPLATE).substitute(pod_template_subs))

    CLOUD_CONFIG = Template(KUBERNETES_CLOUD_TEMPLATE).substitute(
        JENKINS_URL=JENKINS_URL,
        JENKINS_TUNNEL=JENKINS_TUNNEL,
        NAME=NAME,
        POD_TEMPLATES='\n'.join(pod_templates),
    )
    return CLOUD_CONFIG


def translate_mesos_to_k8s_config_xml(src_file: str, target_file: str):
    log.info(f'using "{src_file}" file to migrate to kubernetes configuration at "{target_file}"')

    # Defaults with provided values.yaml
    # Update according to output of "helm2 list jenkins --output json" if needed
    global JENKINS_FULL_NAME
    global JENKINS_NAMESPACE
    global JENKINS_URI_PREFIX
    global JENKINS_URL
    global JENKINS_TUNNEL
    global JENKINS_AGENT_ENTRYPOINT
    JENKINS_FULL_NAME = os.getenv("JENKINS_FULL_NAME")
    JENKINS_NAMESPACE = os.getenv("JENKINS_NAMESPACE")
    JENKINS_URI_PREFIX = os.getenv("JENKINS_URI_PREFIX")
    JENKINS_URL = "http://{}.{}.svc:8080{}".format(JENKINS_FULL_NAME, JENKINS_NAMESPACE, JENKINS_URI_PREFIX)
    JENKINS_TUNNEL = "jenkins-agent.{}:50000".format(JENKINS_NAMESPACE)

    JENKINS_AGENT_ENTRYPOINT = '/bin/sh -c "wget {}/jnlpJars/agent.jar && mkdir -p /usr/share/jenkins && mv agent.jar /usr/share/jenkins && cp /var/configmaps/jenkins-agent /usr/local/bin/jenkins-agent && chmod +x /usr/local/bin/jenkins-agent && jenkins-agent"'.format(
        JENKINS_URL)
    # Currently supported plugin versions
    SUPPORTED_VERSIONS = {
        "mesos@1.0.0": plugin100Transform,
    }

    root = ET.parse(src_file).getroot()

    clouds = root.find("./clouds")

    mesos_cloud_tag = 'org.jenkinsci.plugins.mesos.MesosCloud'
    modified = False
    num_of_clouds = len(clouds)
    for i in range(num_of_clouds):
        cloud = clouds[i]
        if cloud.tag != mesos_cloud_tag:
            log.info('Cloud %s is not supported yet' % cloud.tag)
            continue

        ver = cloud.get("plugin")
        if ver not in SUPPORTED_VERSIONS:
            log.info('Cloud %s with version %s is not supported yet' % (cloud.tag, ver))
            continue

        new_cloud_str = SUPPORTED_VERSIONS[ver](cloud)
        if new_cloud_str is None:
            log.info('Failed to transform cloud %s with version %s' % (cloud.tag, ver))
            continue

        modified = True
        # log.info("-------------------\n\n\n {} \n\n\n----------------------".format(new_cloud_str))
        clouds[i] = ET.fromstring(new_cloud_str)
        log.info(
            f'Completed translation of "{mesos_cloud_tag}" @ "{ver}" in the config file to the Kubernetes Cloud configuration'
        )

    if not modified:
        # Write to a file.
        log.info("No clouds were transformed")
        return

    ET.ElementTree(root).write(open(target_file, 'wb'), encoding='utf-8', xml_declaration=True)
    pretty_xml = xml.dom.minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    return pretty_xml
