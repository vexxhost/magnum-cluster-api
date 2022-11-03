from magnum import objects
from oslo_utils import strutils


def get_cluster_label_as_bool(
    cluster: objects.Cluster, key: str, default: bool
) -> bool:
    value = get_cluster_label(cluster, key, default)
    return strutils.bool_from_string(value, strict=True)


def get_cluster_label_as_int(cluster: objects.Cluster, key: str, default: int) -> int:
    value = get_cluster_label(cluster, key, default)
    return strutils.validate_integer(value, key)


def get_cluster_label(cluster: objects.Cluster, key: str, default: str) -> str:
    return cluster.labels.get(
        key, get_cluster_template_label(cluster.cluster_template, key, default)
    )


def get_cluster_template_label(
    cluster_template: objects.ClusterTemplate, key: str, default: str
) -> str:
    return cluster_template.labels.get(key, default)
