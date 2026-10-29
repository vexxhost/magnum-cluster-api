//! String helpers that behave exactly like their counterparts in
//! [`oslo_utils.strutils`](https://docs.openstack.org/oslo.utils/latest/reference/strutils.html),
//! so the Rust and Python halves of the driver interpret OpenStack inputs
//! such as Magnum labels the same way.

use thiserror::Error;

/// Strings `bool_from_string` treats as `true`, after trimming and lowercasing.
pub const TRUE_STRINGS: [&str; 6] = ["1", "t", "true", "on", "y", "yes"];

/// Strings `bool_from_string` treats as `false`, after trimming and lowercasing.
pub const FALSE_STRINGS: [&str; 6] = ["0", "f", "false", "off", "n", "no"];

#[derive(Debug, Error, PartialEq)]
#[error(
    "Unrecognized value '{0}', acceptable values are: \
     '0', '1', 'f', 'false', 'n', 'no', 'off', 'on', 't', 'true', 'y', 'yes'"
)]
pub struct UnrecognizedBool(pub String);

/// Interprets a string as a boolean, like
/// `oslo_utils.strutils.bool_from_string(subject, strict=True)`.
///
/// Matching is case-insensitive and ignores surrounding whitespace.  Anything
/// outside [`TRUE_STRINGS`] and [`FALSE_STRINGS`], including an empty string,
/// is an error with the same message oslo raises.
pub fn bool_from_string(subject: &str) -> Result<bool, UnrecognizedBool> {
    let lowered = subject.trim().to_lowercase();

    if TRUE_STRINGS.contains(&lowered.as_str()) {
        Ok(true)
    } else if FALSE_STRINGS.contains(&lowered.as_str()) {
        Ok(false)
    } else {
        Err(UnrecognizedBool(subject.to_owned()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::rstest;

    #[rstest]
    fn test_true_strings(#[values("1", "t", "true", "on", "y", "yes")] value: &str) {
        assert_eq!(bool_from_string(value), Ok(true));
        assert_eq!(bool_from_string(&value.to_uppercase()), Ok(true));
        assert_eq!(bool_from_string(&format!(" {value}\n")), Ok(true));
    }

    #[rstest]
    fn test_false_strings(#[values("0", "f", "false", "off", "n", "no")] value: &str) {
        assert_eq!(bool_from_string(value), Ok(false));
        assert_eq!(bool_from_string(&value.to_uppercase()), Ok(false));
        assert_eq!(bool_from_string(&format!(" {value}\n")), Ok(false));
    }

    #[rstest]
    fn test_unrecognized(#[values("", " ", "2", "-1", "enabled", "yess", "maybe")] value: &str) {
        assert_eq!(
            bool_from_string(value),
            Err(UnrecognizedBool(value.to_owned()))
        );
    }

    /// The message matches oslo's `ValueError` text.
    #[test]
    fn test_error_message() {
        assert_eq!(
            bool_from_string("maybe").unwrap_err().to_string(),
            "Unrecognized value 'maybe', acceptable values are: \
             '0', '1', 'f', 'false', 'n', 'no', 'off', 'on', 't', 'true', 'y', 'yes'"
        );
    }
}
