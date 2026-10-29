//! Parse human-entered boolean strings, such as configuration values and
//! labels.
//!
//! ```
//! assert_eq!(boolstr::parse("Yes"), Ok(true));
//! assert_eq!(boolstr::parse(" off "), Ok(false));
//! assert!(boolstr::parse("maybe").is_err());
//! ```
//!
//! The accepted strings and the case and whitespace handling are the same as
//! OpenStack's `oslo_utils.strutils.bool_from_string(value, strict=True)`, so
//! values parsed here and in OpenStack Python services always agree.

use thiserror::Error;

/// Strings parsed as `true`, after trimming and lowercasing.
pub const TRUE: [&str; 6] = ["1", "t", "true", "on", "y", "yes"];

/// Strings parsed as `false`, after trimming and lowercasing.
pub const FALSE: [&str; 6] = ["0", "f", "false", "off", "n", "no"];

/// The input isn't one of the [`TRUE`] or [`FALSE`] strings.
#[derive(Debug, Error, PartialEq)]
#[error(
    "unrecognized boolean value '{0}', expected one of \
     1, t, true, on, y, yes, 0, f, false, off, n or no"
)]
pub struct Error(pub String);

/// Parses `value` as a boolean.
///
/// Matching ignores case and surrounding whitespace.  Anything outside
/// [`TRUE`] and [`FALSE`], including an empty string, is an [`Error`].
pub fn parse(value: &str) -> Result<bool, Error> {
    let lowered = value.trim().to_lowercase();

    if TRUE.contains(&lowered.as_str()) {
        Ok(true)
    } else if FALSE.contains(&lowered.as_str()) {
        Ok(false)
    } else {
        Err(Error(value.to_owned()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::rstest;

    #[rstest]
    fn test_true(#[values("1", "t", "true", "on", "y", "yes")] value: &str) {
        assert_eq!(parse(value), Ok(true));
        assert_eq!(parse(&value.to_uppercase()), Ok(true));
        assert_eq!(parse(&format!(" {value}\n")), Ok(true));
    }

    #[rstest]
    fn test_false(#[values("0", "f", "false", "off", "n", "no")] value: &str) {
        assert_eq!(parse(value), Ok(false));
        assert_eq!(parse(&value.to_uppercase()), Ok(false));
        assert_eq!(parse(&format!(" {value}\n")), Ok(false));
    }

    #[rstest]
    fn test_unrecognized(#[values("", " ", "2", "-1", "enabled", "yess", "maybe")] value: &str) {
        assert_eq!(parse(value), Err(Error(value.to_owned())));
    }
}
