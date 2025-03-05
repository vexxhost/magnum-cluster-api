use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
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
}

/// Runs `helm template` for the given chart, feeding in the provided
/// structured values (which are serialized to YAML) via standard input.
///
/// # Arguments
///
/// * `chart` - The name or path of the Helm chart.
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
) -> Result<Vec<serde_yaml::Value>, HelmTemplateError> {
    let yaml_values = serde_yaml::to_string(values)?;

    let mut child = Command::new("helm")
        .arg("template")
        .arg("--namespace")
        .arg(namespace)
        .arg("--values")
        .arg("-")
        .arg(name)
        .arg(chart)
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

    let output_str = String::from_utf8_lossy(&output.stdout).into_owned();

    let docs: Vec<serde_yaml::Value> = serde_yaml::Deserializer::from_str(&output_str)
        .map(serde_yaml::Value::deserialize)
        .collect::<Result<_, _>>()
        .map_err(HelmTemplateError::Deserialization)?;

    Ok(docs)
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
