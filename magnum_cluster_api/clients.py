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
from keystoneauth1 import exceptions as ka_exception  # type: ignore
from keystoneauth1 import loading as ka_loading  # type: ignore
from keystoneauth1.access import access as ka_access  # type: ignore
from keystoneauth1.identity import access as ka_access_plugin  # type: ignore
from keystoneauth1.identity import v3 as ka_v3  # type: ignore
from magnum.common import clients, exception  # type: ignore
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


def _get_legacy_auth():
    conf = CONF[ksconf.CFG_LEGACY_GROUP]
    return ka_v3.Password(
        auth_url=get_auth_url(),
        username=conf.admin_user,
        password=conf.admin_password,
        project_name=conf.admin_tenant_name,
        project_domain_id="default",
        user_domain_id="default",
    )


def _get_auth(context):
    if getattr(context, "auth_token_info", None):
        access_info = ka_access.create(
            body=context.auth_token_info,
            auth_token=getattr(context, "auth_token", None),
        )
        return ka_access_plugin.AccessInfoPlugin(
            auth_ref=access_info,
            auth_url=get_auth_url(),
        )

    if getattr(context, "auth_token", None):
        return ka_v3.Token(auth_url=get_auth_url(), token=context.auth_token)

    if getattr(context, "trust_id", None):
        return ka_v3.Password(
            auth_url=get_auth_url(),
            username=context.user_name,
            password=context.password,
            user_domain_id=context.user_domain_id,
            user_domain_name=context.user_domain_name,
            trust_id=context.trust_id,
        )

    if getattr(context, "is_admin", False):
        try:
            return ka_loading.load_auth_from_conf_options(CONF, ksconf.CFG_GROUP)
        except ka_exception.MissingRequiredOptions:
            return _get_legacy_auth()

    msg = "Keystone API connection failed: no password, trust_id or token found."
    LOG.error(msg)
    raise exception.AuthorizationFailure(client="keystone", message="reason %s" % msg)


def get_openstack_session(context):
    session = ka_loading.load_session_from_conf_options(CONF, ksconf.CFG_GROUP)
    session.auth = _get_auth(context)
    return session


def get_openstack_connection(context):
    return sdk_connection.Connection(session=get_openstack_session(context))


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
