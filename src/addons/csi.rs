use crate::{
    addons::{ImageDetails},
};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIComponent {
    pub image: ImageDetails,
}
