use std::fmt;

/// Compatibility status of a Kubernetes version with magnum-cluster-api.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KubeVersionStatus {
    /// Fully supported and tested.
    Supported,
    /// Still functional but scheduled for removal in a future release.
    Deprecated,
    /// No longer supported; cluster operations may fail.
    Unsupported,
}

impl fmt::Display for KubeVersionStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            KubeVersionStatus::Supported => write!(f, "supported"),
            KubeVersionStatus::Deprecated => write!(f, "deprecated"),
            KubeVersionStatus::Unsupported => write!(f, "unsupported"),
        }
    }
}

/// Central compatibility rules for Kubernetes minor versions.
///
/// Each entry maps a `(major, minor)` pair to its compatibility status.
/// Versions not listed are considered [`KubeVersionStatus::Unsupported`].
///
/// These rules are derived from the CAPI v1.13 workload cluster support
/// matrix (v1.30–v1.36).  All versions within this range are
/// [`KubeVersionStatus::Supported`]; versions outside the range are
/// [`KubeVersionStatus::Unsupported`].
///
/// Reference: <https://github.com/kubernetes-sigs/cluster-api/releases/tag/v1.13.0>
const VERSION_RULES: &[((u64, u64), KubeVersionStatus)] = &[
    ((1, 30), KubeVersionStatus::Supported),
    ((1, 31), KubeVersionStatus::Supported),
    ((1, 32), KubeVersionStatus::Supported),
    ((1, 33), KubeVersionStatus::Supported),
    ((1, 34), KubeVersionStatus::Supported),
    ((1, 35), KubeVersionStatus::Supported),
    ((1, 36), KubeVersionStatus::Supported),
];

/// Parse a `kube_tag` string (e.g. `"v1.35.2"`, `"1.35.2"`) into a
/// [`semver::Version`].
///
/// Returns `None` if the string is empty, missing, or not a valid semver
/// version.
pub fn parse_kube_tag(kube_tag: &str) -> Option<semver::Version> {
    let trimmed = kube_tag.strip_prefix('v').unwrap_or(kube_tag);
    semver::Version::parse(trimmed).ok()
}

/// Return the [`KubeVersionStatus`] for a given `kube_tag`.
///
/// The tag is first normalized via [`parse_kube_tag`]; only the major and minor
/// components are used for the lookup.  Patch versions do not affect
/// compatibility.
///
/// Missing, empty, or unparseable tags return [`KubeVersionStatus::Unsupported`].
pub fn get_compatibility_status(kube_tag: &str) -> KubeVersionStatus {
    let version = match parse_kube_tag(kube_tag) {
        Some(v) => v,
        None => return KubeVersionStatus::Unsupported,
    };

    let key = (version.major, version.minor);
    VERSION_RULES
        .iter()
        .find(|(k, _)| *k == key)
        .map(|(_, status)| *status)
        .unwrap_or(KubeVersionStatus::Unsupported)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::rstest;

    // ── parse_kube_tag ──────────────────────────────────────────────────

    #[rstest]
    #[case("v1.35.2", 1, 35, 2)]
    #[case("v1.31.0", 1, 31, 0)]
    #[case("1.35.2", 1, 35, 2)]
    #[case("v1.28.10", 1, 28, 10)]
    fn test_parse_kube_tag_valid(
        #[case] input: &str,
        #[case] major: u64,
        #[case] minor: u64,
        #[case] patch: u64,
    ) {
        let version = parse_kube_tag(input).expect("should parse");
        assert_eq!(version.major, major);
        assert_eq!(version.minor, minor);
        assert_eq!(version.patch, patch);
    }

    #[rstest]
    #[case("")]
    #[case("invalid")]
    #[case("master")]
    #[case("v")]
    #[case("v1")]
    #[case("v1.35")]
    #[case("latest")]
    fn test_parse_kube_tag_invalid(#[case] input: &str) {
        assert!(parse_kube_tag(input).is_none(), "expected None for {input:?}");
    }

    // ── get_compatibility_status — supported ────────────────────────────

    #[rstest]
    #[case("v1.30.0")]
    #[case("v1.30.3")]
    #[case("v1.31.0")]
    #[case("v1.31.4")]
    #[case("v1.32.0")]
    #[case("v1.32.1")]
    #[case("v1.33.0")]
    #[case("v1.33.12")]
    #[case("v1.34.0")]
    #[case("v1.34.8")]
    #[case("v1.35.0")]
    #[case("v1.35.5")]
    #[case("v1.36.0")]
    #[case("v1.36.1")]
    #[case("1.36.1")]
    fn test_status_supported(#[case] tag: &str) {
        assert_eq!(get_compatibility_status(tag), KubeVersionStatus::Supported);
    }

    // ── get_compatibility_status — unsupported ──────────────────────────

    #[rstest]
    #[case("v1.29.0")]
    #[case("v1.28.0")]
    #[case("v1.27.0")]
    #[case("v1.22.0")]
    #[case("v1.25.3")]
    #[case("v2.0.0")]
    #[case("v1.60.0")]
    fn test_status_unsupported_old_or_unknown(#[case] tag: &str) {
        assert_eq!(
            get_compatibility_status(tag),
            KubeVersionStatus::Unsupported,
        );
    }

    #[rstest]
    #[case("")]
    #[case("invalid")]
    #[case("master")]
    #[case("v")]
    #[case("latest")]
    fn test_status_unsupported_unparseable(#[case] tag: &str) {
        assert_eq!(
            get_compatibility_status(tag),
            KubeVersionStatus::Unsupported,
        );
    }

    // ── Display impl ────────────────────────────────────────────────────

    #[test]
    fn test_display() {
        assert_eq!(KubeVersionStatus::Supported.to_string(), "supported");
        assert_eq!(KubeVersionStatus::Deprecated.to_string(), "deprecated");
        assert_eq!(KubeVersionStatus::Unsupported.to_string(), "unsupported");
    }

    // ── patch version does not affect status ────────────────────────────

    #[test]
    fn test_patch_version_irrelevant() {
        assert_eq!(
            get_compatibility_status("v1.33.0"),
            get_compatibility_status("v1.33.99"),
        );
        assert_eq!(
            get_compatibility_status("v1.30.0"),
            get_compatibility_status("v1.30.15"),
        );
        assert_eq!(
            get_compatibility_status("v1.36.0"),
            get_compatibility_status("v1.36.99"),
        );
    }
}
