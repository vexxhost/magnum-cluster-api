use cached::proc_macro::io_cached;
use std::fs;
use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use tempfile::NamedTempFile;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum KubeadmImageRetrieveError {
    #[error("request error: {0}")]
    RequestError(#[from] reqwest::Error),

    #[error("io error: {0}")]
    IOError(#[from] std::io::Error),

    #[error("failed to parse UTF-8 from output: {0}")]
    Utf8Error(#[from] std::string::FromUtf8Error),

    #[error("failed to execute kubeadm")]
    CommandExecutionFailed,

    #[error("error with disk cache `{0}`")]
    DiskError(String),
}

#[io_cached(
    map_error = r##"|e| KubeadmImageRetrieveError::DiskError(format!("{:?}", e))"##,
    disk = true
)]
pub fn get_kubeadm_images_for_version(
    version: &str,
) -> Result<Vec<String>, KubeadmImageRetrieveError> {
    let url = format!(
        "https://dl.k8s.io/release/{}/bin/linux/amd64/kubeadm",
        version
    );

    let response = reqwest::blocking::get(&url)?.error_for_status()?;
    let bytes = response.bytes()?;

    let mut temp_file = NamedTempFile::new()?;
    temp_file.write_all(&bytes)?;
    let temp_path = temp_file.into_temp_path();

    let metadata = fs::metadata(&temp_path)?;
    let mut permissions = metadata.permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&temp_path, permissions)?;

    let output = std::process::Command::new(&temp_path)
        .args(["config", "images", "list", "--kubernetes-version", version])
        .output()?;

    if !output.status.success() {
        return Err(KubeadmImageRetrieveError::CommandExecutionFailed);
    }

    let output_str = String::from_utf8(output.stdout)?;
    let images = output_str
        .replace("k8s.gcr.io", "registry.k8s.io")
        .lines()
        .map(String::from)
        .collect();

    Ok(images)
}
