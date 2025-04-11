use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::get_runtime;
use std::future::Future;

pub fn block_in_place_and_wait<T, E, F>(
    py: Python,
    f: impl FnOnce() -> F + Sync + Send,
) -> Result<T, E>
where
    F: Future<Output = Result<T, E>>,
    T: Send,
    E: Send,
{
    py.allow_threads(|| {
        let future = f();
        tokio::task::block_in_place(|| get_runtime().block_on(future))
    })
}
