use crate::GLOBAL_RUNTIME;
use kube::{Client, Config};
use pyo3::{exceptions, PyErr};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error(transparent)]
    Infer(#[from] kube::config::InferConfigError),

    #[error(transparent)]
    Client(#[from] kube::Error),
}

impl From<Error> for PyErr {
    fn from(err: Error) -> PyErr {
        match err {
            Error::Infer(e) => PyErr::new::<exceptions::PyValueError, _>(format!(
                "Failed to load KUBECONFIG: {}",
                e
            )),
            Error::Client(e) => PyErr::new::<exceptions::PyRuntimeError, _>(format!(
                "Failed to create client: {}",
                e
            )),
        }
    }
}

pub fn new() -> Result<Client, Error> {
    GLOBAL_RUNTIME.block_on(async {
        let config = Config::infer().await?;
        Client::try_from(config).map_err(Error::Client)
    })
}
