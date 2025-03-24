mod addons;
mod client;
mod clients;
mod cluster_api;
mod driver;
mod features;
mod magnum;
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
    m.add_class::<driver::Driver>()?;
    m.add_class::<monitor::Monitor>()?;

    Ok(())
}
