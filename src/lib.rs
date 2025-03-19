mod addons;
mod client;
mod cluster_api;
mod features;
mod kube;
mod magnum;
mod models;
mod monitor;
mod resources;

use once_cell::sync::Lazy;
use pyo3::{prelude::*, Bound};
use tokio::runtime::{Builder, Runtime};

static GLOBAL_RUNTIME: Lazy<Runtime> = Lazy::new(|| {
    Builder::new_multi_thread()
        .enable_all()
        .build()
        .expect("Failed to create Tokio runtime")
});

#[pymodule]
fn magnum_cluster_api(m: &Bound<'_, PyModule>) -> PyResult<()> {
    pyo3_log::init();

    m.add_class::<client::KubeClient>()?;
    m.add_class::<models::MagnumCluster>()?;
    m.add_class::<monitor::Monitor>()?;

    Ok(())
}
