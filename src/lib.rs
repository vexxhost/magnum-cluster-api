mod client;
mod models;
mod cluster_api;
mod features;

use pyo3::{prelude::*, Bound};

#[pymodule]
fn magnum_cluster_api(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<client::KubeClient>()?;
    m.add_class::<models::MagnumCluster>()?;

    Ok(())
}
