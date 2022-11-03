import pykube
from magnum.common import clients


def get_pykube_api() -> pykube.HTTPClient:
    return pykube.HTTPClient(pykube.KubeConfig.from_env())


def get_openstack_api(context) -> clients.OpenStackClients:
    return clients.OpenStackClients(context)
