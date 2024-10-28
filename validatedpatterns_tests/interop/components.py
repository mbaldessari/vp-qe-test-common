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


def validate_site_reachable(kube_config, openshift_dyn_client):
    logger.info("Check if site API end point is reachable")
    api_url = kube_config.host
    if not api_url:
        err_msg = "Site url is missing in kubeconfig file"
        assert False, err_msg
    else:
        logger.info(f"api url : {api_url}")

    bearer_token = get_long_live_bearer_token(
        dyn_client=openshift_dyn_client,
        namespace="openshift-gitops",
        sub_string="argocd-dex-server-token",
    )

    if not bearer_token:
        assert False, "Bearer token is missing for argocd-dex-server"

    api_response = get_site_response(
        site_url=edge_api_url, bearer_token=bearer_token
    )

    return api_response

    # if edge_api_response.status_code != 200:
    #     err_msg = "Edge site is not reachable. Please check the deployment."
    #     logger.error(f"FAIL: {err_msg}")
    #     assert False, err_msg
    # else:
    #     logger.info("PASS: Edge site is reachable")