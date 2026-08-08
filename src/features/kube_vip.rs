use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources,
        },
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables, ClusterClassVariables, ClusterClassVariablesSchema,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "kubeVip", default)]
    pub kube_vip: bool,
    #[serde(rename = "kubeVipImage", default)]
    pub kube_vip_image: String,
    #[serde(rename = "kubeVipInterface", default)]
    pub kube_vip_interface: String,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        let kube_vip_template = r#"
path: /etc/kubernetes/manifests/kube-vip.yaml
owner: root:root
permissions: "0600"
content: |
  apiVersion: v1
  kind: Pod
  metadata:
    name: kube-vip
    namespace: kube-system
  spec:
    containers:
    - args:
      - manager
      env:
      - name: vip_arp
        value: "true"
      - name: port
        value: "6443"
      - name: vip_nodename
        valueFrom:
          fieldRef:
            fieldPath: spec.nodeName
      - name: vip_interface
        value: "{{ .kubeVipInterface }}"
      - name: vip_cidr
        value: "32"
      - name: dns_mode
        value: "first"
      - name: cp_enable
        value: "true"
      - name: cp_namespace
        value: kube-system
      - name: vip_leaderelection
        value: "true"
      - name: vip_leasename
        value: plndr-cp-lock
      - name: vip_leaseduration
        value: "5"
      - name: vip_renewdeadline
        value: "3"
      - name: vip_retryperiod
        value: "1"
      - name: address
        value: "{{ .apiServerFixedIP }}"
      - name: prometheus_server
        value: :2112
      image: {{ .kubeVipImage }}
      imagePullPolicy: IfNotPresent
      name: kube-vip
      securityContext:
        capabilities:
          add:
          - NET_ADMIN
          - NET_RAW
      volumeMounts:
      - mountPath: /etc/kubernetes/admin.conf
        name: kubeconfig
      - mountPath: /etc/ssl/certs
        name: ca-certs
        readOnly: true
    hostNetwork: true
    hostAliases:
      - hostnames:
          - kubernetes
        ip: 127.0.0.1
    volumes:
    - hostPath:
        path: /etc/kubernetes/super-admin.conf
      name: kubeconfig
    - hostPath:
        path: /etc/ssl/certs
      name: ca-certs
"#;

        vec![ClusterClassPatches {
            name: "kubeVip".into(),
            enabled_if: Some("{{ if and .kubeVip .apiServerFixedIPManaged (ne .kubeVipInterface \"\") }}true{{end}}".into()),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
                selector: ClusterClassPatchesDefinitionsSelector {
                    api_version: KubeadmControlPlaneTemplate::api_resource().api_version,
                    kind: KubeadmControlPlaneTemplate::api_resource().kind,
                    match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                        control_plane: Some(true),
                        ..Default::default()
                    },
                },
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(kube_vip_template.into()),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
            }]),
            ..Default::default()
        }]
    }
}

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;
    use crate::resources::fixtures::default_values;

    #[test]
    fn renders_only_with_an_explicit_vip_and_interface() {
        let mut values = default_values();
        values.kube_vip = true;
        values.api_server_fixed_ip = "10.20.8.70".into();
        values.api_server_fixed_ip_managed = true;
        values.kube_vip_interface = "ens212f0np0".into();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&Feature {}.patches(), &values);
        let files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .expect("control-plane files should be present");
        let manifest = files
            .iter()
            .find(|file| file.path == "/etc/kubernetes/manifests/kube-vip.yaml")
            .expect("kube-vip manifest should be rendered");
        let content = manifest.content.as_deref().expect("manifest content");
        assert!(content.contains("value: \"ens212f0np0\""));
        assert!(content.contains("value: \"10.20.8.70\""));
        assert!(content.contains("mountPath: /etc/kubernetes/admin.conf"));
        assert!(content.contains("path: /etc/kubernetes/super-admin.conf"));
    }

    #[test]
    fn omits_the_manifest_without_an_interface() {
        let mut values = default_values();
        values.kube_vip = true;
        values.api_server_fixed_ip = "10.20.8.70".into();
        values.api_server_fixed_ip_managed = true;

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&Feature {}.patches(), &values);
        assert!(resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .unwrap_or_default()
            .iter()
            .all(|file| file.path != "/etc/kubernetes/manifests/kube-vip.yaml"));
    }
}
