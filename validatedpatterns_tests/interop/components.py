import logging
import os
import subprocess
import yaml

from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from openshift.dynamic.exceptions import NotFoundError

from . import __loggername__
from validatedpatterns_tests.interop import application
from validatedpatterns_tests.interop.crd import ManagedCluster

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


def check_project_absence(openshift_dyn_client, projects):
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


def check_pod_status(openshift_dyn_client, projects):
    missing_projects = check_project_absence(openshift_dyn_client, projects)
    missing_pods = []
    failed_pods = []
    err_msg = []

    for project in projects:
        logger.info(f"Checking pods in namespace '{project}'")
        missing_pods += check_pod_absence(openshift_dyn_client, project)
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

    if missing_projects:
        err_msg.append(f"The following namespaces are missing: {missing_projects}")

    if missing_pods:
        err_msg.append(
            f"The following namespaces have no pods deployed: {missing_pods}"
        )

    if failed_pods:
        err_msg.append(f"The following pods are failed: {failed_pods}")

    if err_msg:
        return False, err_msg
    else:
        return None


def validate_site_reachable(kube_config, openshift_dyn_client):
    namespace = "openshift-gitops"
    sub_string = "argocd-dex-server-token"

    api_url = application.get_site_api_url(kube_config)
    api_response = application.get_site_api_response(
        openshift_dyn_client, api_url, namespace, sub_string
    )

    logger.info(f"Site API response : {api_response}")

    if api_response.status_code != 200:
        err_msg = "Site is not reachable. Please check the deployment."
        return False, err_msg
    else:
        return None


def validate_argocd_reachable(openshift_dyn_client):
    namespace = "openshift-gitops"
    name = "openshift-gitops-server"
    sub_string = "argocd-dex-server-token"
    logger.info("Check if argocd route/url on hub site is reachable")
    try:
        argocd_route_url = application.get_argocd_route_url(
            openshift_dyn_client, namespace, name
        )
        argocd_route_response = application.get_site_api_response(
            openshift_dyn_client, argocd_route_url, namespace, sub_string
        )
    except StopIteration:
        err_msg = "Argocd url/route is missing in open-cluster-management namespace"
        assert False, err_msg

    logger.info(f"Argocd route response : {argocd_route_response}")

    if argocd_route_response.status_code != 200:
        err_msg = "Argocd is not reachable. Please check the deployment"
        return False, err_msg
    else:
        return None


def validate_acm_self_registration_managed_clusters(openshift_dyn_client, kubefiles):
    err_msg = []
    for kubefile in kubefiles:
        kubefile_exp = os.path.expandvars(kubefile)
        with open(kubefile_exp) as stream:
            try:
                out = yaml.safe_load(stream)
                site_name = out["clusters"][0]["name"]
            except yaml.YAMLError:
                err_msg = "Failed to load kubeconfig file"
                assert False, err_msg

        clusters = ManagedCluster.get(dyn_client=openshift_dyn_client, name=site_name)
        cluster = next(clusters)
        is_managed_cluster_joined, managed_cluster_status = cluster.self_registered

        logger.info(f"Cluster Managed : {is_managed_cluster_joined}")
        logger.info(f"Managed Cluster Status : {managed_cluster_status}")

        if not is_managed_cluster_joined:
            err_msg += f"{site_name} is not self registered"
            # logger.error(f"FAIL: {err_msg}")
            # return False, err_msg
        else:
            return None

    return err_msg
