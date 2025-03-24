use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use typed_builder::TypedBuilder;

// NOTE(mnaser): This is temporary until the following is addressed
//
//               - https://github.com/gtema/openstack/issues/1082

#[derive(Clone, Debug, Deserialize, Serialize, TypedBuilder)]
pub struct CloudConfigFile {
    pub clouds: HashMap<String, CloudConfig>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum EndpointType {
    Public,
    Internal,
    Admin,
}

#[derive(Clone, Debug, Deserialize, Serialize, TypedBuilder)]
pub struct CloudConfig {
    #[builder(default = "v3applicationcredential".to_owned())]
    pub auth_type: String,

    pub auth: CloudConfigAuth,

    #[builder(default = EndpointType::Public)]
    pub endpoint_type: EndpointType,

    #[builder(default = 3)]
    pub identity_api_version: u8,

    #[builder(default = "RegionOne".to_owned())]
    pub region_name: String,

    #[builder(default = true)]
    pub verify: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize, TypedBuilder)]
pub struct CloudConfigAuth {
    pub application_credential_id: String,
    pub application_credential_secret: String,
    pub auth_url: String,
}
