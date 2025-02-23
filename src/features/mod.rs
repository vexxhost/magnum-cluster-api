#[cfg(test)]
mod test;

mod audit_log;
mod api_server_load_balancer;
mod keystone_auth;
mod openid_connect;
mod server_groups;

use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassVariables, ClusterClassVariablesSchema,
};
use schemars::{gen::SchemaGenerator, JsonSchema};

pub trait ClusterFeature {
    fn variables(&self) -> Vec<ClusterClassVariables>;
    fn patches(&self) -> Vec<ClusterClassPatches>;
}

pub trait ClusterClassVariablesSchemaExt {
    fn from_object<T: JsonSchema>() -> Self;
    fn from_root_schema(root_schema: schemars::schema::RootSchema) -> Self;
}

impl ClusterClassVariablesSchemaExt for ClusterClassVariablesSchema {
    fn from_object<T: JsonSchema>() -> Self {
        let gen = SchemaGenerator::default();
        let schema = gen.into_root_schema_for::<T>();
        Self::from_root_schema(schema)
    }

    fn from_root_schema(root_schema: schemars::schema::RootSchema) -> Self {
        let json_schema = serde_json::to_string(&root_schema).unwrap();

        ClusterClassVariablesSchema {
            open_apiv3_schema: serde_json::from_str(&json_schema).unwrap(),
        }
    }
}
