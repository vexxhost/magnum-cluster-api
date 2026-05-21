# Copyright (c) 2023 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import magnum.conf  # type: ignore
import pykube  # type: ignore
from magnum.common import clients, exception  # type: ignore
from magnum.common import keystone as magnum_keystone  # type: ignore
from magnum.conf import keystone as ksconf  # type: ignore
from magnum.i18n import _  # type: ignore
from manilaclient.v2 import client as manilaclient  # type: ignore
from openstack import connection as sdk_connection  # type: ignore
from openstack import exceptions as sdk_exceptions  # type: ignore
from oslo_config import cfg  # type: ignore
from oslo_log import log as logging  # type: ignore

CONF = magnum.conf.CONF
LOG = logging.getLogger(__name__)


def _get_conf_option(group, option):
    try:
        return getattr(CONF[group], option)
    except (cfg.NoSuchGroupError, cfg.NoSuchOptError):
        return None


def get_auth_url():
    auth_url = _get_conf_option(ksconf.CFG_GROUP, "auth_url")
    if not auth_url:
        auth_url = _get_conf_option(
            ksconf.CFG_LEGACY_GROUP, "www_authenticate_uri"
        ) or _get_conf_option(
            ksconf.CFG_LEGACY_GROUP,
            "auth_uri",
        )
    if auth_url:
        return auth_url.replace("v2.0", "v3")
    return auth_url


def get_openstack_session(context):
    return magnum_keystone.KeystoneClientV3(context).session


def _normalize_interface(endpoint_type):
    return {
        "publicURL": "public",
        "internalURL": "internal",
        "adminURL": "admin",
    }.get(endpoint_type, endpoint_type)


def _get_connection_options():
    endpoint_type = (
        _get_conf_option(ksconf.CFG_GROUP, "interface")
        or _get_conf_option(ksconf.CFG_LEGACY_GROUP, "interface")
        or get_client_option("cinder", "endpoint_type")
    )
    region_name = (
        _get_conf_option(ksconf.CFG_GROUP, "region_name")
        or _get_conf_option(ksconf.CFG_LEGACY_GROUP, "region_name")
        or get_client_option("cinder", "region_name")
    )

    options = {}
    if endpoint_type:
        options["interface"] = _normalize_interface(endpoint_type)
    if region_name:
        options["region_name"] = region_name
    return options


def get_openstack_connection(context):
    return sdk_connection.Connection(
        session=get_openstack_session(context),
        **_get_connection_options(),
    )


def get_client_option(client, option):
    return getattr(getattr(CONF, "%s_client" % client), option)


def get_validate_region_name(connection, region_name):
    if region_name is None:
        message = _("region_name needs to be configured in magnum.conf")
        raise exception.InvalidParameterValue(message)

    try:
        regions = list(connection.identity.regions())
    except sdk_exceptions.NotFoundException:
        regions = []
    except Exception:
        LOG.exception("Failed to list regions")
        raise exception.RegionsListFailed()

    region_list = [region.id for region in regions]
    if region_name not in region_list:
        raise exception.InvalidParameterValue(
            _(
                "region_name %(region_name)s is invalid, "
                "expecting a region_name in %(region_name_list)s."
            )
            % {
                "region_name": region_name,
                "region_name_list": "/".join(region_list + ["unspecified"]),
            }
        )
    return region_name


def get_cinder_region_name(connection):
    return get_validate_region_name(
        connection,
        get_client_option("cinder", "region_name"),
    )


class OpenStackClients(clients.OpenStackClients):
    """Convenience class to create and cache client instances."""

    def __init__(self, context):
        super(OpenStackClients, self).__init__(context)
        self._manila = None
        self._session = None

    @property
    def auth_url(self):
        return get_auth_url()

    @property
    def auth_token(self):
        return getattr(self.context, "auth_token", None) or self.session.get_token()

    @property
    def session(self):
        if self._session:
            return self._session

        self._session = get_openstack_session(self.context)
        return self._session

    def url_for(self, **kwargs):
        return self.session.get_endpoint(**kwargs)

    def cinder_region_name(self):
        return get_cinder_region_name(get_openstack_connection(self.context))

    @exception.wrap_keystone_exception
    def manila(self):
        if self._manila:
            return self._manila
        endpoint_type = self._get_client_option("manila", "endpoint_type")
        region_name = self._get_client_option("manila", "region_name")
        manilaclient_version = self._get_client_option("manila", "api_version")
        endpoint = self.url_for(
            service_type="sharev2", interface=endpoint_type, region_name=region_name
        )
        args = {
            "cacert": self._get_client_option("manila", "ca_file"),
            "insecure": self._get_client_option("manila", "insecure"),
        }

        session = self.session
        self._manila = manilaclient.Client(
            manilaclient_version, session=session, service_catalog_url=endpoint, **args
        )
        return self._manila


def get_pykube_api() -> pykube.HTTPClient:
    return pykube.HTTPClient(pykube.KubeConfig.from_env())


def get_openstack_api(context) -> OpenStackClients:
    return OpenStackClients(context)
