mod addons;
mod client;
mod cluster_api;
mod features;
mod magnum;
mod models;
mod resources;

use pyo3::{prelude::*, Bound};

#[pymodule]
fn magnum_cluster_api(m: &Bound<'_, PyModule>) -> PyResult<()> {
    pyo3_log::init();

    m.add_class::<client::KubeClient>()?;
    m.add_class::<models::MagnumCluster>()?;

    Ok(())
}
