import difflib
import logging
import os
import re
import subprocess

from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.subscription import Subscription
from openshift.dynamic.exceptions import NotFoundError

from . import __loggername__

logger = logging.getLogger(__loggername__)


def openshift_version(openshift_dyn_client):
    versions = ClusterVersion.get(dyn_client=openshift_dyn_client)
    version = next(versions)
    logger.info(f"Openshift version:\n{version.instance.status.history}")

    return version


def subscription_status(openshift_dyn_client, expected_subs, diff):
    operator_versions = []
    missing_subs = []
    unhealthy_subs = []
    missing_installplans = []
    upgrades_pending = []

    for key in expected_subs.keys():
        for val in expected_subs[key]:
            try:
                subs = Subscription.get(
                    dyn_client=openshift_dyn_client, name=key, namespace=val
                )
                sub = next(subs)
            except NotFoundError:
                missing_subs.append(f"{key} in {val} namespace")
                continue

            logger.info(
                f"State for {sub.instance.metadata.name}: {sub.instance.status.state}"
            )
            if sub.instance.status.state == "UpgradePending":
                upgrades_pending.append(
                    f"{sub.instance.metadata.name} in {sub.instance.metadata.namespace} namespace"
                )

            logger.info(
                f"CatalogSourcesUnhealthy: {sub.instance.status.conditions[0].status}"
            )
            if sub.instance.status.conditions[0].status != "False":
                logger.info(f"Subscription {sub.instance.metadata.name} is unhealthy")
                unhealthy_subs.append(
                    f"{sub.instance.metadata.name} in {sub.instance.metadata.namespace} namespace"
                )
            else:
                operator_versions.append(
                    f"installedCSV: {sub.instance.status.installedCSV}"
                )

            logger.info(f"installPlanRef: {sub.instance.status.installPlanRef}")
            if not sub.instance.status.installPlanRef:
                logger.info(
                    f"No install plan found for subscription {sub.instance.metadata.name} "
                    f"in {sub.instance.metadata.namespace} namespace"
                )
                missing_installplans.append(
                    f"{sub.instance.metadata.name} in {sub.instance.metadata.namespace} namespace"
                )

            logger.info("")

    if missing_subs:
        logger.error(f"FAIL: The following subscriptions are missing: {missing_subs}")
    if unhealthy_subs:
        logger.error(
            f"FAIL: The following subscriptions are unhealthy: {unhealthy_subs}"
        )
    if missing_installplans:
        logger.error(
            f"FAIL: The install plan for the following subscriptions is missing: {missing_installplans}"
        )
    if upgrades_pending:
        logger.error(
            f"FAIL: The following subscriptions are in UpgradePending state: {upgrades_pending}"
        )

    cluster_version = openshift_version(openshift_dyn_client)
    logger.info(f"Openshift version:\n{cluster_version.instance.status.history}")

    if (os.getenv("EXTERNAL_TEST") != "true") and (diff == True):
        shortversion = re.sub("(.[0-9]+$)", "", os.getenv("OPENSHIFT_VER"))
        currentfile = os.getcwd() + "/operators_hub_current"
        sourceFile = open(currentfile, "w")
        for line in operator_versions:
            logger.info(line)
            print(line, file=sourceFile)
        sourceFile.close()

        logger.info("Clone operator-versions repo")
        try:
            operator_versions_repo = (
                "git@gitlab.cee.redhat.com:mpqe/mps/vp/operator-versions.git"
            )
            clone = subprocess.run(
                ["git", "clone", operator_versions_repo], capture_output=True, text=True
            )
            logger.info(clone.stdout)
            logger.info(clone.stderr)
        except Exception:
            pass

        pattern = os.getenv("PATTERN_SHORTNAME")
        previouspath = os.getcwd() + f"/operator-versions/{pattern}_hub_{shortversion}"
        previousfile = f"{pattern}_hub_{shortversion}"

        logger.info("Ensure previous file exists")
        checkpath = os.path.exists(previouspath)
        logger.info(checkpath)

        if checkpath is True:
            logger.info("Diff current operator list with previous file")
            diff = opdiff(open(previouspath).readlines(), open(currentfile).readlines())
            diffstring = "".join(diff)
            logger.info(diffstring)

            logger.info("Write diff to file")
            sourceFile = open("operator_diffs_hub.log", "w")
            print(diffstring, file=sourceFile)
            sourceFile.close()
        else:
            logger.info("Skipping operator diff - previous file not found")

    if missing_subs or unhealthy_subs or missing_installplans or upgrades_pending:
        err_msg = "Subscription status check failed"
        return err_msg
    else:
        # Only push the new operarator list if the test passed
        # and we are not testing a pre-release operator nor
        # running externally
        if (os.getenv("EXTERNAL_TEST") != "true") and (diff == True):
            if checkpath is True and not os.environ["INDEX_IMAGE"]:
                os.remove(previouspath)
                os.rename(currentfile, previouspath)

                cwd = os.getcwd() + "/operator-versions"
                logger.info(f"CWD: {cwd}")

                logger.info("Push new operator list")
                subprocess.run(["git", "add", previousfile], cwd=cwd)
                subprocess.run(
                    ["git", "commit", "-m", "Update operator versions list"],
                    cwd=cwd,
                )
                subprocess.run(["git", "push"], cwd=cwd)

        return None


def opdiff(*args):
    return filter(lambda x: not x.startswith(" "), difflib.ndiff(*args))
