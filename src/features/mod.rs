#[cfg(test)]
mod test;

mod openid_connect;

use cluster_api_rs::capi_clusterclass::{ClusterClassPatches, ClusterClassVariables};

pub trait ClusterFeature {
    fn variables(&self) -> Vec<ClusterClassVariables>;
    fn patches(&self) -> Vec<ClusterClassPatches>;
}
