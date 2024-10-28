import logging

from ocp_resources.route import Route

from . import __loggername__
from .crd import ArgoCD
from .edge_util import get_long_live_bearer_token, get_site_response

logger = logging.getLogger(__loggername__)


def get_site_api_url(kube_config):
    hub_api_url = kube_config.host
    if not hub_api_url:
        err_msg = "Hub site url is missing in kubeconfig file"
        assert False, err_msg
    else:
        logger.info(f"HUB api url : {hub_api_url}")
        return hub_api_url


def get_site_api_response(openshift_dyn_client, site_api_url, project, sub_string):
    bearer_token = get_long_live_bearer_token(
        dyn_client=openshift_dyn_client,
        namespace=project,
        sub_string=sub_string,
    )

    if not bearer_token:
        err_msg = "Bearer token is missing for {}".format(sub_string)
        assert False, err_msg
    else:
        logger.debug(f"Site bearer token : {bearer_token}")

    site_api_response = get_site_response(
        site_url=site_api_url, bearer_token=bearer_token
    )

    return site_api_response


def get_argocd_route_url(openshift_dyn_client, project, name):
    try:
        for route in Route.get(
            dyn_client=openshift_dyn_client,
            namespace=project,
            name=name,
        ):
            argocd_route_url = route.instance.spec.host
    except StopIteration:
        raise

    final_argocd_url = f"{'http://'}{argocd_route_url}"
    logger.info(f"ACM route/url : {final_argocd_url}")

    return final_argocd_url


def get_argocd_application_status(openshift_dyn_client, projects):
    unhealthy_apps = []

    for project in projects:
        for app in ArgoCD.get(dyn_client=openshift_dyn_client, namespace=project):
            app_name = app.instance.metadata.name
            app_health = app.instance.status.health.status
            app_sync = app.instance.status.sync.status

            logger.info(f"Status for {app_name} : {app_health} : {app_sync}")

            if "Healthy" != app_health or "Synced" != app_sync:
                logger.info(f"Dumping failed resources for app: {app_name}")
                unhealthy_apps.append(app_name)
                try:
                    for res in app.instance.status.resources:
                        if (
                            res.health and res.health.status != "Healthy"
                        ) or res.status != "Synced":
                            logger.info(f"\n{res}")
                except TypeError:
                    logger.info(f"No resources found for app: {app_name}")

    return unhealthy_apps


def validate_argocd_reachable(openshift_dyn_client):
    namespace = "openshift-gitops"

    try:
        for route in Route.get(
            dyn_client=openshift_dyn_client,
            namespace=namespace,
            name="openshift-gitops-server",
        ):
            argocd_route_url = route.instance.spec.host
    except StopIteration:
        err_msg = f"Argocd url/route is missing in {namespace} namespace"
        assert False, err_msg

    logger.info("Check if argocd route/url on hub site is reachable")
    if not argocd_route_url:
        err_msg = f"Argocd url/route is missing in {namespace} namespace"
        assert False, err_msg
    else:
        final_argocd_url = f"{'https://'}{argocd_route_url}"
        logger.info(f"Argocd route/url : {final_argocd_url}")

    bearer_token = get_long_live_bearer_token(
        dyn_client=openshift_dyn_client,
        namespace=namespace,
        sub_string="argocd-dex-server-token",
    )
    if not bearer_token:
        err_msg = "Bearer token is missing for argocd-dex-server"
        assert False, err_msg
    else:
        logger.debug(f"Argocd bearer token : {bearer_token}")

    argocd_route_response = get_site_response(
        site_url=final_argocd_url, bearer_token=bearer_token
    )

    logger.info(f"Argocd route response : {argocd_route_response}")

    # if argocd_route_response.status_code != 200:
    #     err_msg = "Argocd is not reachable. Please check the deployment."
    #     logger.error(f"FAIL: {err_msg}")
    #     assert False, err_msg
    # else:
    #     logger.info("PASS: Argocd is reachable")