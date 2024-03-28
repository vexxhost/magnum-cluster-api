mod registry;

use pyo3::prelude::*;
use rand::{distributions::Alphanumeric, Rng};
use rayon::prelude::*;
use slug::slugify;

#[pyfunction]
fn convert_to_rfc1123(input: &str) -> String {
    slugify(input)
}

#[pyfunction]
fn generate_cluster_name() -> String {
    let random_string: String = rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .filter(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        .take(5)
        .map(char::from)
        .collect();

    format!("kube-{}", random_string)
}

#[pyfunction]
fn get_kubeadm_images(versions: Vec<&str>) -> PyResult<Vec<String>> {
    let images: Vec<Vec<String>> = versions
        .par_iter()
        .map(|version| registry::get_kubeadm_images_for_version(version))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("{}", e)))?;

    Ok(images.into_iter().flatten().collect())
}

#[pymodule]
#[pyo3(name = "_internal")]
fn magnum_cluster_api(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(convert_to_rfc1123, m)?)?;
    m.add_function(wrap_pyfunction!(generate_cluster_name, m)?)?;
    m.add_function(wrap_pyfunction!(get_kubeadm_images, m)?)?;

    Ok(())
}
