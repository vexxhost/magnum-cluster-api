use crate::{clients::kubernetes, cluster_api::clusterclasses::ClusterClass};
use kube::{
    api::{Api, Patch, PatchParams},
    Client,
};
use log::debug;
use semver::Version;
use serde_yaml::{Mapping, Value};

const APT_PROXY_PATH: &str = "/etc/apt/apt.conf.d/90proxy";
const APT_PROXY_VARIABLE: &str = "aptProxyConfig";
const APT_PROXY_PLACEHOLDER_TEMPLATE: &str =
    r#"{{ if ne .aptProxyConfig "" }}{{ .aptProxyConfig }}{{ else }}Iw=={{ end }}"#;
const SYSTEMD_PROXY_PATH: &str = "/etc/systemd/system/containerd.service.d/proxy.conf";
const SYSTEMD_PROXY_VARIABLE: &str = "systemdProxyConfig";
const SYSTEMD_PROXY_PLACEHOLDER_TEMPLATE: &str =
    r#"{{ if ne .systemdProxyConfig "" }}{{ .systemdProxyConfig }}{{ else }}Iw=={{ end }}"#;

pub async fn repair_legacy_proxy_file_patches(
    client: Client,
    namespace: &str,
    cluster_class_name: &str,
) -> Result<bool, kubernetes::Error> {
    let api: Api<ClusterClass> = Api::namespaced(client, namespace);
    if !should_repair_cluster_class(cluster_class_name) {
        return Ok(false);
    }

    let mut cluster_class = api.get(cluster_class_name).await?;
    if !repair_proxy_file_content_templates(&mut cluster_class) {
        return Ok(false);
    }

    let patch = serde_json::json!({
        "spec": {
            "patches": cluster_class.spec.patches,
        },
    });
    api.patch(
        cluster_class_name,
        &PatchParams::default(),
        &Patch::Merge(&patch),
    )
    .await?;
    debug!("repaired legacy proxy file patches in ClusterClass {cluster_class_name}");

    Ok(true)
}

fn should_repair_cluster_class(name: &str) -> bool {
    if name == *crate::CLUSTER_CLASS_NAME {
        return false;
    }

    magnum_cluster_class_version(name)
        .is_some_and(|version| version < proxy_patch_guard_fix_version())
}

fn magnum_cluster_class_version(name: &str) -> Option<Version> {
    let version = name.strip_prefix("magnum-v")?;
    let base_version = version.split('-').next().unwrap_or(version);

    Version::parse(base_version).ok()
}

fn proxy_patch_guard_fix_version() -> Version {
    Version::new(0, 36, 1)
}

pub(crate) fn repair_proxy_file_content_templates(cluster_class: &mut ClusterClass) -> bool {
    let mut changed = false;

    if let Some(patches) = &mut cluster_class.spec.patches {
        for patch in patches {
            let enabled_if = patch.enabled_if.as_deref();
            if let Some(definitions) = &mut patch.definitions {
                for definition in definitions {
                    for json_patch in &mut definition.json_patches {
                        if let Some(value_from) = &mut json_patch.value_from {
                            if let Some(template) = &mut value_from.template {
                                changed |= repair_proxy_file_template(template, enabled_if);
                            }
                        }
                    }
                }
            }
        }
    }

    changed
}

fn repair_proxy_file_template(template: &mut String, enabled_if: Option<&str>) -> bool {
    let Ok(mut file) = serde_yaml::from_str::<Value>(template) else {
        return false;
    };

    let Some(file_map) = file.as_mapping_mut() else {
        return false;
    };

    let Some(path) = get_str(file_map, "path") else {
        return false;
    };

    let Some((variable, placeholder_template)) = proxy_file_repair(path) else {
        return false;
    };

    if patch_guards_variable(enabled_if, variable) {
        return false;
    }

    let expected_content_template = format!("{{{{ .{variable} }}}}");
    if get_str(file_map, "content") != Some(expected_content_template.as_str()) {
        return false;
    }

    file_map.insert(
        Value::String("content".into()),
        Value::String(placeholder_template.into()),
    );
    *template = serde_yaml::to_string(&file).expect("proxy file template should serialize");

    true
}

fn proxy_file_repair(path: &str) -> Option<(&'static str, &'static str)> {
    match path {
        APT_PROXY_PATH => Some((APT_PROXY_VARIABLE, APT_PROXY_PLACEHOLDER_TEMPLATE)),
        SYSTEMD_PROXY_PATH => Some((SYSTEMD_PROXY_VARIABLE, SYSTEMD_PROXY_PLACEHOLDER_TEMPLATE)),
        _ => None,
    }
}

fn patch_guards_variable(enabled_if: Option<&str>, variable: &str) -> bool {
    enabled_if.is_some_and(|enabled_if| {
        let variable_reference = format!(".{variable}");
        enabled_if.contains("ne")
            && enabled_if.contains(&variable_reference)
            && enabled_if.contains(r#""""#)
    })
}

fn get_str<'a>(map: &'a Mapping, key: &str) -> Option<&'a str> {
    map.get(Value::String(key.into())).and_then(Value::as_str)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cluster_api::clusterclasses::{
        ClusterClassPatches, ClusterClassPatchesDefinitions,
        ClusterClassPatchesDefinitionsJsonPatches,
        ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    };
    use pretty_assertions::assert_eq;

    #[test]
    fn targets_only_cluster_classes_before_proxy_patch_guards() {
        assert!(should_repair_cluster_class("magnum-v0.34.2"));
        assert!(should_repair_cluster_class("magnum-v0.36.0"));
        assert!(should_repair_cluster_class("magnum-v0.36.0-4-gabcdef"));
        assert!(!should_repair_cluster_class("magnum-v0.36.1"));
        assert!(!should_repair_cluster_class("magnum-v0.36.1-1-gabcdef"));
        assert!(!should_repair_cluster_class("magnum-v0.36.7"));
        assert!(!should_repair_cluster_class("other-v0.34.2"));
    }

    fn proxy_file_template(path: &str, content: &str) -> String {
        serde_yaml::to_string(&serde_json::json!({
            "path": path,
            "owner": "root:root",
            "permissions": "0644",
            "encoding": "base64",
            "content": content,
        }))
        .unwrap()
    }

    fn patch(name: &str, enabled_if: Option<&str>, templates: Vec<String>) -> ClusterClassPatches {
        ClusterClassPatches {
            name: name.into(),
            enabled_if: enabled_if.map(str::to_string),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
                selector: ClusterClassPatchesDefinitionsSelector::default(),
                json_patches: templates
                    .into_iter()
                    .map(|template| ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                        value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                            template: Some(template),
                            ..Default::default()
                        }),
                        ..Default::default()
                    })
                    .collect(),
            }]),
            ..Default::default()
        }
    }

    fn template_content(template: &str) -> String {
        let value = serde_yaml::from_str::<Value>(template).unwrap();
        value
            .as_mapping()
            .unwrap()
            .get(Value::String("content".into()))
            .unwrap()
            .as_str()
            .unwrap()
            .to_string()
    }

    #[test]
    fn repairs_legacy_empty_proxy_templates() {
        let mut cluster_class = ClusterClass::new("magnum-v0.34.2", Default::default());
        cluster_class.spec.patches = Some(vec![
            patch(
                "ubuntu",
                Some(r#"{{ if eq .operatingSystem "ubuntu" }}true{{end}}"#),
                vec![proxy_file_template(APT_PROXY_PATH, "{{ .aptProxyConfig }}")],
            ),
            patch(
                "containerdConfig",
                None,
                vec![
                    proxy_file_template(SYSTEMD_PROXY_PATH, "{{ .systemdProxyConfig }}"),
                    proxy_file_template("/etc/containerd/config.toml", "{{ .containerdConfig }}"),
                ],
            ),
        ]);

        assert!(repair_proxy_file_content_templates(&mut cluster_class));

        let patches = cluster_class.spec.patches.unwrap();
        let apt_template = patches[0].definitions.as_ref().unwrap()[0].json_patches[0]
            .value_from
            .as_ref()
            .unwrap()
            .template
            .as_ref()
            .unwrap();
        assert_eq!(
            template_content(apt_template),
            APT_PROXY_PLACEHOLDER_TEMPLATE
        );

        let systemd_template = patches[1].definitions.as_ref().unwrap()[0].json_patches[0]
            .value_from
            .as_ref()
            .unwrap()
            .template
            .as_ref()
            .unwrap();
        assert_eq!(
            template_content(systemd_template),
            SYSTEMD_PROXY_PLACEHOLDER_TEMPLATE
        );

        let containerd_template = patches[1].definitions.as_ref().unwrap()[0].json_patches[1]
            .value_from
            .as_ref()
            .unwrap()
            .template
            .as_ref()
            .unwrap();
        assert_eq!(
            template_content(containerd_template),
            "{{ .containerdConfig }}"
        );
    }

    #[test]
    fn does_not_repair_already_guarded_proxy_templates() {
        let mut cluster_class = ClusterClass::new("magnum-v0.36.1", Default::default());
        cluster_class.spec.patches = Some(vec![
            patch(
                "aptProxyConfig",
                Some(
                    r#"{{ if and (eq .operatingSystem "ubuntu") (ne .aptProxyConfig "") }}true{{end}}"#,
                ),
                vec![proxy_file_template(APT_PROXY_PATH, "{{ .aptProxyConfig }}")],
            ),
            patch(
                "systemdProxyConfig",
                Some(r#"{{ if ne .systemdProxyConfig "" }}true{{end}}"#),
                vec![proxy_file_template(
                    SYSTEMD_PROXY_PATH,
                    "{{ .systemdProxyConfig }}",
                )],
            ),
        ]);

        assert!(!repair_proxy_file_content_templates(&mut cluster_class));
    }

    #[test]
    fn repair_is_idempotent() {
        let mut cluster_class = ClusterClass::new("magnum-v0.34.2", Default::default());
        cluster_class.spec.patches = Some(vec![patch(
            "containerdConfig",
            None,
            vec![proxy_file_template(
                SYSTEMD_PROXY_PATH,
                "{{ .systemdProxyConfig }}",
            )],
        )]);

        assert!(repair_proxy_file_content_templates(&mut cluster_class));
        assert!(!repair_proxy_file_content_templates(&mut cluster_class));
    }
}
