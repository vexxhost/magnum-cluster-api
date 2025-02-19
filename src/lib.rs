mod client;

use pyo3::{prelude::*, Bound};

#[pymodule]
fn magnum_cluster_api(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<client::KubeClient>()?;

    Ok(())
}
