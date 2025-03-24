use crate::magnum;
use k8s_openapi::api::core::v1::Secret;
use pyo3::{prelude::*, types::PyType};
use std::collections::BTreeMap;

#[pyclass]
pub struct MagnumCluster {
    #[pyo3(get)]
    namespace: String,

    #[pyo3(get)]
    uuid: String,

    #[pyo3(get)]
    cluster_class_name: String,
}

#[pymethods]
impl MagnumCluster {
    #[new]
    #[pyo3(signature = (obj, cluster_class_name, namespace = "magnum-system"))]
    fn new(
        py: Python<'_>,
        obj: PyObject,
        cluster_class_name: &str,
        namespace: &str,
    ) -> PyResult<Self> {
        let uuid: String = obj.getattr(py, "uuid")?.extract(py)?;

        Ok(MagnumCluster {
            uuid,
            namespace: namespace.to_string(),
            cluster_class_name: cluster_class_name.to_string(),
        })
    }

    #[classmethod]
    #[pyo3(signature = (cluster))]
    fn get_config_data(
        _cls: &Bound<'_, PyType>,
        cluster: PyObject,
        py: Python<'_>,
    ) -> PyResult<Option<BTreeMap<String, String>>> {
        let cluster: magnum::Cluster = cluster.extract(py)?;
        let config_map = Secret::from(&cluster);
        Ok(config_map.string_data)
    }
}
