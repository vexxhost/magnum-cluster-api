use include_dir::Dir;
use serde::{Deserialize, Serialize};
use serde_yaml::Value;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use tempfile::TempDir;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum HelmTemplateError {
    #[error("failed to serialize values to yaml: {0}")]
    Serialization(#[from] serde_yaml::Error),

    #[error("failed to spawn helm: {0}")]
    Spawn(std::io::Error),

    #[error("failed to open stdin for helm process")]
    StdinUnavailable,

    #[error("failed to write to helm stdin: {0}")]
    StdinWrite(std::io::Error),

    #[error("failed to wait on helm process: {0}")]
    Wait(std::io::Error),

    #[error("helm command returned an error: {0}")]
    HelmCommand(String),

    #[error("failed to deserialize helm output: {0}")]
    Deserialization(serde_yaml::Error),

    #[error("failed to create temporary directory: {0}")]
    TempDir(std::io::Error),

    #[error("failed to extract chart: {0}")]
    Extract(std::io::Error),
}

/// Options for helm template command
#[derive(Debug, Default)]
pub struct TemplateOptions {
    /// Include CRDs in the templated output (--include-crds flag)
    pub include_crds: bool,
}

/// Runs `helm template` for the given chart, feeding in the provided
/// structured values (which are serialized to YAML) via standard input.
///
/// # Arguments
///
/// * `chart` - The name or path of the Helm chart.
/// * `name` - The release name.
/// * `namespace` - The namespace for the release.
/// * `values` - A reference to any structure that implements `Serialize`.
///
/// # Returns
///
/// * `Ok(String)` with the templated output if the command succeeds.
/// * `Err(HelmTemplateError)` with the error if something goes wrong.
pub fn template<T: Serialize>(
    chart: &PathBuf,
    name: &str,
    namespace: &str,
    values: &T,
) -> Result<String, HelmTemplateError> {
    template_with_options(chart, name, namespace, values, TemplateOptions::default())
}

/// Runs `helm template` with additional options.
///
/// # Arguments
///
/// * `chart` - The name or path of the Helm chart.
/// * `name` - The release name.
/// * `namespace` - The namespace for the release.
/// * `values` - A reference to any structure that implements `Serialize`.
/// * `options` - Template options (include_crds, etc.)
///
/// # Returns
///
/// * `Ok(String)` with the templated output if the command succeeds.
/// * `Err(HelmTemplateError)` with the error if something goes wrong.
pub fn template_with_options<T: Serialize>(
    chart: &PathBuf,
    name: &str,
    namespace: &str,
    values: &T,
    options: TemplateOptions,
) -> Result<String, HelmTemplateError> {
    let yaml_values = serde_yaml::to_string(values)?;

    let mut cmd = Command::new("helm");
    cmd.arg("template")
        .arg("--namespace")
        .arg(namespace)
        .arg("--values")
        .arg("-");

    if options.include_crds {
        cmd.arg("--include-crds");
    }

    cmd.arg(name).arg(chart);

    let mut child = cmd
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(HelmTemplateError::Spawn)?;

    {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or(HelmTemplateError::StdinUnavailable)?;
        stdin
            .write_all(yaml_values.as_bytes())
            .map_err(HelmTemplateError::StdinWrite)?;
    }

    let output = child.wait_with_output().map_err(HelmTemplateError::Wait)?;

    if !output.status.success() {
        let error_str = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return Err(HelmTemplateError::HelmCommand(error_str));
    }

    let raw_output = String::from_utf8_lossy(&output.stdout).into_owned();

    // Post-process YAML output to add namespace to resources
    // NOTE: ClusterResourceSet fails to be applied without namespace set in resources.
    //       On the other hand, helm template doesn't output namespace. We set it manually.
    //       See: https://github.com/helm/helm/issues/10737
    process_helm_output(&raw_output, namespace)
}

/// Process helm template output to add namespace to resources and filter empty documents.
///
/// Cluster-scoped resources (ClusterRole, ClusterRoleBinding, CustomResourceDefinition)
/// are excluded from namespace injection.
fn process_helm_output(output: &str, namespace: &str) -> Result<String, HelmTemplateError> {
    let mut docs: Vec<Value> = Vec::new();

    for doc in serde_yaml::Deserializer::from_str(output) {
        let value: Value = match Value::deserialize(doc) {
            Ok(v) => v,
            Err(_) => continue, // Skip documents that can't be parsed
        };

        // Skip null/empty documents (can occur with YAML separators when using --include-crds)
        if value.is_null() {
            continue;
        }

        let mut value = value;

        // Get the kind of the resource
        let kind = value
            .get("kind")
            .and_then(|k| k.as_str())
            .unwrap_or_default();

        // Don't add namespace to cluster-scoped resources
        if !matches!(
            kind,
            "ClusterRole" | "ClusterRoleBinding" | "CustomResourceDefinition"
        ) {
            // Add namespace to metadata
            if let Some(metadata) = value.get_mut("metadata") {
                if let Some(metadata_map) = metadata.as_mapping_mut() {
                    metadata_map.insert(
                        Value::String("namespace".to_string()),
                        Value::String(namespace.to_string()),
                    );
                }
            }
        }

        docs.push(value);
    }

    // Serialize all documents back to YAML
    let mut result = String::new();
    for (i, doc) in docs.iter().enumerate() {
        if i > 0 {
            result.push_str("---\n");
        }
        result.push_str(&serde_yaml::to_string(doc)?);
    }

    Ok(result)
}

/// This is a helper function which allows you to use a `Dir` from the `include_dir` crate
/// as the source for the chart.
pub fn template_using_include_dir<T: Serialize>(
    chart: Dir,
    name: &str,
    namespace: &str,
    values: &T,
) -> Result<String, HelmTemplateError> {
    template_using_include_dir_with_options(chart, name, namespace, values, TemplateOptions::default())
}

/// This is a helper function which allows you to use a `Dir` from the `include_dir` crate
/// as the source for the chart, with additional options.
pub fn template_using_include_dir_with_options<T: Serialize>(
    chart: Dir,
    name: &str,
    namespace: &str,
    values: &T,
    options: TemplateOptions,
) -> Result<String, HelmTemplateError> {
    let tmp_dir = TempDir::new().map_err(HelmTemplateError::TempDir)?;
    chart
        .extract(tmp_dir.path())
        .map_err(HelmTemplateError::Extract)?;

    template_with_options(&tmp_dir.path().to_path_buf(), name, namespace, values, options)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Serialize;

    #[derive(Serialize)]
    struct DummyValues {
        replica_count: u32,
        image: Image,
    }

    #[derive(Serialize)]
    struct Image {
        repository: String,
        tag: String,
    }

    #[test]
    fn test_invalid_chart() {
        let values = DummyValues {
            replica_count: 2,
            image: Image {
                repository: "myrepo/myimage".to_string(),
                tag: "latest".to_string(),
            },
        };

        let result = template(
            &PathBuf::from("./nonexistent-chart"),
            "nonexistent-chart",
            "magnum-system",
            &values,
        );
        match result {
            Err(HelmTemplateError::HelmCommand(ref msg)) => {
                assert_eq!(msg, r#"Error: path "./nonexistent-chart" not found"#);
            }
            _ => panic!(
                "Expected HelmTemplateError::HelmCommand, but got: {:?}",
                result
            ),
        }
    }
}
