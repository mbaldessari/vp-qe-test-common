import logging
import os
import subprocess

from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from openshift.dynamic.exceptions import NotFoundError

from . import __loggername__

logger = logging.getLogger(__loggername__)

oc = os.environ["HOME"] + "/oc_client/oc"


def dump_openshift_version():
    version_out = subprocess.run(["oc", "version"], capture_output=True)
    version_out = version_out.stdout.decode("utf-8")
    return version_out


def dump_pvc():
    pvcs_out = subprocess.run(["oc", "get", "pvc", "-A"], capture_output=True)
    pvcs_out = pvcs_out.stdout.decode("utf-8")
    return pvcs_out


def describe_pod(project, pod):
    cmd_out = subprocess.run(
        [oc, "describe", "pod", "-n", project, pod], capture_output=True
    )
    if cmd_out.stdout:
        return cmd_out.stdout.decode("utf-8")
    else:
        assert False, cmd_out.stderr


def get_log_output(project, pod, container):
    cmd_out = subprocess.run(
        [oc, "logs", "-n", project, pod, "-c", container], capture_output=True
    )
    if cmd_out.stdout:
        return cmd_out.stdout.decode("utf-8")
    else:
        assert False, cmd_out.stderr


def check_project_absense(openshift_dyn_client, projects):
    missing_projects = []

    for project in projects:
        # Check for missing project
        try:
            namespaces = Namespace.get(dyn_client=openshift_dyn_client, name=project)
            next(namespaces)
        except NotFoundError:
            missing_projects.append(project)
            continue

    return missing_projects


def check_pod_absence(openshift_dyn_client, project):
    # Check for absence of pods in project
    missing_pods = []
    try:
        pods = Pod.get(dyn_client=openshift_dyn_client, namespace=project)
        next(pods)
    except StopIteration:
        missing_pods.append(project)
    return missing_pods


def check_pod_status(openshift_dyn_client, project):
    failed_pods = []
    pods = Pod.get(dyn_client=openshift_dyn_client, namespace=project)
    for pod in pods:
        for container in pod.instance.status.containerStatuses:
            logger.info(
                f"{pod.instance.metadata.name} : {container.name} :"
                f" {container.state}"
            )
            if container.state.terminated:
                if container.state.terminated.reason != "Completed":
                    logger.info(
                        f"Pod {pod.instance.metadata.name} in"
                        f" {pod.instance.metadata.namespace} namespace is"
                        " FAILED:"
                    )
                    failed_pods.append(pod.instance.metadata.name)
                    logger.info(describe_pod(project, pod.instance.metadata.name))
                    logger.info(
                        get_log_output(
                            project,
                            pod.instance.metadata.name,
                            container.name,
                        )
                    )
            elif not container.state.running:
                logger.info(
                    f"Pod {pod.instance.metadata.name} in"
                    f" {pod.instance.metadata.namespace} namespace is"
                    " FAILED:"
                )
                failed_pods.append(pod.instance.metadata.name)
                logger.info(describe_pod(project, pod.instance.metadata.name))
                logger.info(
                    get_log_output(project, pod.instance.metadata.name, container.name)
                )

    return failed_pods
