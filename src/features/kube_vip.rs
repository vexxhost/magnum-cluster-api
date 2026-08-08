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
    #[serde(rename = "kubeVip")]
    pub kube_vip: bool,
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
        value: "eth0"
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
      image: ghcr.io/kube-vip/kube-vip:v0.8.2
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
        path: /etc/kubernetes/admin.conf
      name: kubeconfig
    - hostPath:
        path: /etc/ssl/certs
      name: ca-certs
"#;

        vec![ClusterClassPatches {
            name: "kubeVip".into(),
            enabled_if: Some("{{ if .kubeVip }}true{{end}}".into()),
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
