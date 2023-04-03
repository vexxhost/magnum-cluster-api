import shutil
import subprocess

AUTOSCALER_HELM_REPO_NAME = "autoscaler"
AUTOSCALER_HELM_REPO_URL = "https://kubernetes.github.io/autoscaler"
AUTOSCALER_HELM_CHART = "cluster-autoscaler"
AUTOSCALER_HELM_VERSION = "9.27.0"


def setup_helm_repository(name, url):
    subprocess.run(["helm", "repo", "add", name, url])
    subprocess.run(["helm", "repo", "update"])


def download_helm_chart(repo, chart, version):
    shutil.rmtree(f"magnum_cluster_api/charts/{chart}", ignore_errors=True)
    subprocess.run(
        [
            "helm",
            "fetch",
            f"{repo}/{chart}",
            "--version",
            version,
            "--untar",
            "--untardir",
            "magnum_cluster_api/charts",
        ]
    )


def download_autoscaler_chart():
    setup_helm_repository(AUTOSCALER_HELM_REPO_NAME, AUTOSCALER_HELM_REPO_URL)
    download_helm_chart(
        AUTOSCALER_HELM_REPO_NAME, AUTOSCALER_HELM_CHART, AUTOSCALER_HELM_VERSION
    )


if __name__ == "__main__":
    download_autoscaler_chart()
