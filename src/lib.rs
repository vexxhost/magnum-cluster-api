mod addons;
mod r#async;
mod client;
mod clients;
mod cluster_api;
mod driver;
mod features;
mod magnum;
mod monitor;
mod resources;

use pyo3::{prelude::*, Bound};

#[pymodule]
fn magnum_cluster_api(m: &Bound<'_, PyModule>) -> PyResult<()> {
    pyo3_log::init();

    m.add_class::<client::KubeClient>()?;
    m.add_class::<driver::Driver>()?;
    m.add_class::<monitor::Monitor>()?;

    Ok(())
}
