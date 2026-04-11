mod addons;
mod client;
mod clients;
mod cluster_api;
mod driver;
mod features;
pub mod immutable_fields;
mod magnum;
mod monitor;
mod resources;

use pyo3::{prelude::*, Bound};
use std::sync::LazyLock;

pub static CLUSTER_CLASS_NAME: LazyLock<String> =
    LazyLock::new(|| format!("magnum-{}", env!("VERGEN_GIT_DESCRIBE")));

// Compile-time assertion: VERGEN_GIT_DESCRIBE must not be empty.
const _: () = assert!(
    !env!("VERGEN_GIT_DESCRIBE").is_empty(),
    "VERGEN_GIT_DESCRIBE is empty — git tags may be missing from the build environment",
);

#[pymodule]
fn magnum_cluster_api(m: &Bound<'_, PyModule>) -> PyResult<()> {
    pyo3_log::init();

    m.add("CLUSTER_CLASS_NAME", CLUSTER_CLASS_NAME.as_str())?;
    m.add_class::<client::KubeClient>()?;
    m.add_class::<driver::Driver>()?;
    m.add_class::<monitor::Monitor>()?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// RFC 1123 subdomain: lowercase alphanumeric, '-' or '.', must start
    /// and end with an alphanumeric character.
    fn is_rfc1123_subdomain(name: &str) -> bool {
        if name.is_empty() || name.len() > 253 {
            return false;
        }
        let re = regex::Regex::new(
            r"^[a-z0-9]([a-z0-9.\-]*[a-z0-9])?$"
        ).unwrap();
        re.is_match(name)
    }

    #[test]
    fn cluster_class_name_is_valid_rfc1123() {
        assert!(
            is_rfc1123_subdomain(&CLUSTER_CLASS_NAME),
            "CLUSTER_CLASS_NAME {:?} is not a valid RFC 1123 subdomain",
            *CLUSTER_CLASS_NAME,
        );
    }

    #[test]
    fn cluster_class_name_is_not_empty_suffix() {
        assert_ne!(
            *CLUSTER_CLASS_NAME, "magnum-",
            "CLUSTER_CLASS_NAME must not have an empty suffix",
        );
    }
}
