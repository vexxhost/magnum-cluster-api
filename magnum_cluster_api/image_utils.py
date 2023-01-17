def get_image(name: str, repository: str = None):
    """
    Get the image name from the target registry given a full image name.
    """

    if repository is None:
        return repository

    new_image_name = name
    if name.startswith("docker.io/calico"):
        new_image_name = name.replace("docker.io/calico/", f"{repository}/calico-")
    if name.startswith("docker.io/k8scloudprovider"):
        new_image_name = name.replace("docker.io/k8scloudprovider", repository)
    if name.startswith("k8s.gcr.io/sig-storage"):
        new_image_name = name.replace("k8s.gcr.io/sig-storage", repository)
    if new_image_name.startswith(f"{repository}/livenessprobe"):
        return new_image_name.replace("livenessprobe", "csi-livenessprobe")
    if new_image_name.startswith("k8s.gcr.io/coredns"):
        return new_image_name.replace("k8s.gcr.io/coredns", repository)
    if (
        new_image_name.startswith("k8s.gcr.io/etcd")
        or new_image_name.startswith("k8s.gcr.io/kube-")
        or new_image_name.startswith("k8s.gcr.io/pause")
    ):
        return new_image_name.replace("k8s.gcr.io", repository)

    assert new_image_name.startswith(repository) is True
    return new_image_name

