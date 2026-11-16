#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "PyGithub>=2.6,<3",
#   "PyYAML>=6.0.2,<7",
# ]
# ///

"""Update cloud-provider-openstack releases, charts, and image defaults."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml
from github import Auth, Github
from github.GithubException import GithubException, UnknownObjectException

RELEASE_REPOSITORY = "kubernetes/cloud-provider-openstack"
MINIMUM_KUBERNETES_MINOR = 22

CHART_NAMES = (
    "openstack-cloud-controller-manager",
    "openstack-cinder-csi",
    "openstack-manila-csi",
)
CINDER_CHART = "openstack-cinder-csi"
MANILA_CHART = "openstack-manila-csi"

SEMVER_RE = r"(?P<major>[0-9]+)\.(?P<minor>[0-9]+)\.(?P<patch>[0-9]+)"
CPO_TAG_RE = re.compile(rf"^v{SEMVER_RE}$")


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def from_match(cls, match: re.Match[str]) -> Version:
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseInfo:
    default_tag: str
    tags_by_minor: tuple[tuple[int, str], ...]
    chart_versions: dict[str, str]


@dataclass(frozen=True)
class ChartDocuments:
    chart: dict[str, Any]
    values: dict[str, Any]


@dataclass(frozen=True)
class ImageTagSource:
    chart: str
    values_path: tuple[str, ...] | None = None


IMAGE_TAG_SOURCES: dict[str, tuple[ImageTagSource, ...]] = {
    "cinder_csi_plugin_tag": (ImageTagSource(CINDER_CHART),),
    "manila_csi_plugin_tag": (ImageTagSource(MANILA_CHART),),
    "csi_attacher_tag": (
        ImageTagSource(CINDER_CHART, ("csi", "attacher", "image", "tag")),
    ),
    "csi_liveness_probe_tag": (
        ImageTagSource(CINDER_CHART, ("csi", "livenessprobe", "image", "tag")),
    ),
    "csi_node_driver_registrar_tag": (
        ImageTagSource(
            CINDER_CHART,
            ("csi", "nodeDriverRegistrar", "image", "tag"),
        ),
        ImageTagSource(
            MANILA_CHART,
            ("nodeplugin", "registrar", "image", "tag"),
        ),
    ),
    "csi_provisioner_tag": (
        ImageTagSource(CINDER_CHART, ("csi", "provisioner", "image", "tag")),
        ImageTagSource(
            MANILA_CHART,
            ("controllerplugin", "provisioner", "image", "tag"),
        ),
    ),
    "csi_resizer_tag": (
        ImageTagSource(CINDER_CHART, ("csi", "resizer", "image", "tag")),
        ImageTagSource(
            MANILA_CHART,
            ("controllerplugin", "resizer", "image", "tag"),
        ),
    ),
    "csi_snapshotter_tag": (
        ImageTagSource(CINDER_CHART, ("csi", "snapshotter", "image", "tag")),
        ImageTagSource(
            MANILA_CHART,
            ("controllerplugin", "snapshotter", "image", "tag"),
        ),
    ),
}


class IndentedDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
        return super().increase_indent(flow, False)


def matching_version(name: str, pattern: re.Pattern[str]) -> Version | None:
    match = pattern.fullmatch(name)
    return Version.from_match(match) if match else None


def release_info(tag_names: list[str], release_tags: list[str]) -> ReleaseInfo:
    versions_by_minor: dict[int, Version] = {}
    for name in tag_names:
        version = matching_version(name, CPO_TAG_RE)
        if (
            version is None
            or version.major != 1
            or version.minor < MINIMUM_KUBERNETES_MINOR
        ):
            continue
        versions_by_minor[version.minor] = max(
            version,
            versions_by_minor.get(version.minor, version),
        )

    if not versions_by_minor:
        raise ScriptError("No supported cloud-provider-openstack tags were found")

    cpo_releases = [
        version
        for name in release_tags
        if (version := matching_version(name, CPO_TAG_RE)) is not None
    ]
    if not cpo_releases:
        raise ScriptError("No cloud-provider-openstack release was found")

    chart_versions: dict[str, str] = {}
    for chart in CHART_NAMES:
        pattern = re.compile(rf"^{re.escape(chart)}-{SEMVER_RE}$")
        versions = [
            version
            for name in release_tags
            if (version := matching_version(name, pattern)) is not None
        ]
        if not versions:
            raise ScriptError(f"No {chart} chart release was found")
        chart_versions[chart] = str(max(versions))

    return ReleaseInfo(
        default_tag=f"v{max(cpo_releases)}",
        tags_by_minor=tuple(
            (minor, f"v{version}")
            for minor, version in sorted(versions_by_minor.items())
        ),
        chart_versions=chart_versions,
    )


def latest_releases(repository: str) -> ReleaseInfo:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    github = Github(auth=Auth.Token(token)) if token else Github()

    try:
        repo = github.get_repo(repository)
        tag_names = [tag.name for tag in repo.get_tags()]
        release_tags = [
            release.tag_name
            for release in repo.get_releases()
            if release.tag_name and not release.draft and not release.prerelease
        ]
        return release_info(tag_names, release_tags)
    except UnknownObjectException as exc:
        raise ScriptError(f"Unable to find repository {repository}") from exc
    except GithubException as exc:
        message = str(exc)
        if isinstance(exc.data, dict) and exc.data.get("message"):
            message = str(exc.data["message"])
        raise ScriptError(
            f"GitHub API request failed for {repository}: {message}"
        ) from exc
    finally:
        github.close()


def yaml_mapping(text: str, source: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScriptError(f"Unable to parse {source}: {exc}") from exc
    if not isinstance(document, dict):
        raise ScriptError(f"Expected {source} to contain a YAML mapping")
    return document


def dump_yaml(document: dict[str, Any]) -> str:
    return yaml.dump(
        document,
        Dumper=IndentedDumper,
        sort_keys=False,
        width=4096,
    )


def update_chart_versions(text: str, versions: dict[str, str]) -> str:
    document = yaml_mapping(text, ".charts.yml")
    charts = document.get("charts")
    if not isinstance(charts, list):
        raise ScriptError("Expected .charts.yml to contain a charts list")

    found: set[str] = set()
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        name = chart.get("name")
        if name in versions:
            if name in found:
                raise ScriptError(f"Chart {name} is configured more than once")
            chart["version"] = versions[name]
            found.add(name)

    missing = set(versions) - found
    if missing:
        raise ScriptError(
            f"Charts missing from .charts.yml: {', '.join(sorted(missing))}"
        )

    return dump_yaml(document)


def configured_chart_versions(text: str) -> dict[str, str]:
    document = yaml_mapping(text, ".charts.yml")
    charts = document.get("charts")
    if not isinstance(charts, list):
        raise ScriptError("Expected .charts.yml to contain a charts list")

    versions: dict[str, str] = {}
    for chart in charts:
        if not isinstance(chart, dict) or chart.get("name") not in CHART_NAMES:
            continue
        name = chart["name"]
        version = chart.get("version")
        if not isinstance(version, str) or not version:
            raise ScriptError(f"Chart {name} has no version")
        if name in versions:
            raise ScriptError(f"Chart {name} is configured more than once")
        versions[name] = version

    missing = set(CHART_NAMES) - set(versions)
    if missing:
        raise ScriptError(
            f"Charts missing from .charts.yml: {', '.join(sorted(missing))}"
        )
    return versions


def load_chart_documents(charts_root: Path) -> dict[str, ChartDocuments]:
    documents = {}
    for chart in CHART_NAMES:
        chart_root = charts_root / chart
        documents[chart] = ChartDocuments(
            chart=yaml_mapping(
                (chart_root / "Chart.yaml").read_text(),
                f"{chart}/Chart.yaml",
            ),
            values=yaml_mapping(
                (chart_root / "values.yaml").read_text(),
                f"{chart}/values.yaml",
            ),
        )
    return documents


def nested_value(document: dict[str, Any], path: tuple[str, ...], source: str) -> Any:
    value: Any = document
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ScriptError(f"Missing {'.'.join(path)} in {source}")
        value = value[key]
    return value


def image_defaults_from_charts(
    documents: dict[str, ChartDocuments],
) -> dict[str, str]:
    defaults = {}
    for field, sources in IMAGE_TAG_SOURCES.items():
        tags = []
        for source in sources:
            document = documents.get(source.chart)
            if document is None:
                raise ScriptError(f"Missing vendored chart {source.chart}")
            if source.values_path is None:
                tag = document.chart.get("appVersion")
                location = f"{source.chart}/Chart.yaml appVersion"
            else:
                tag = nested_value(
                    document.values,
                    source.values_path,
                    f"{source.chart}/values.yaml",
                )
                location = f"{source.chart}/values.yaml {'.'.join(source.values_path)}"
            if not isinstance(tag, str) or not tag:
                raise ScriptError(f"Expected a non-empty image tag at {location}")
            tags.append(tag)

        if len(set(tags)) != 1:
            raise ScriptError(
                f"Vendored charts disagree on {field}: {', '.join(sorted(set(tags)))}"
            )
        defaults[field] = tags[0]
    return defaults


def replace_once(
    text: str,
    pattern: re.Pattern[str],
    replacement: str,
    description: str,
) -> str:
    updated, count = pattern.subn(lambda _: replacement, text)
    if count != 1:
        raise ScriptError(f"Expected exactly one {description}, found {count}")
    return updated


def single_match(
    text: str,
    pattern: re.Pattern[str],
    description: str,
) -> re.Match[str]:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ScriptError(f"Expected exactly one {description}, found {len(matches)}")
    return matches[0]


def replace_span(text: str, span: tuple[int, int], replacement: str) -> str:
    start, end = span
    return text[:start] + replacement + text[end:]


def update_rust_source(
    text: str,
    releases: ReleaseInfo,
    image_defaults: dict[str, str],
) -> str:
    default_pattern = re.compile(
        r'^    const DEFAULT_CLOUD_PROVIDER_TAG: &\'static str = "[^"]+";$',
        re.MULTILINE,
    )
    text = replace_once(
        text,
        default_pattern,
        f'    const DEFAULT_CLOUD_PROVIDER_TAG: &\'static str = "{releases.default_tag}";',
        "DEFAULT_CLOUD_PROVIDER_TAG constant",
    )

    match_pattern = re.compile(
        r"(?P<start>^        match \(version\.major, version\.minor\) \{\n)"
        r".*?"
        r"(?P<end>^            _ => Self::DEFAULT_CLOUD_PROVIDER_TAG\.to_owned\(\),\n)",
        re.MULTILINE | re.DOTALL,
    )
    match = single_match(
        text,
        match_pattern,
        "Kubernetes cloud-provider match block",
    )
    match_lines = "".join(
        f'            (1, {minor}) => "{tag}".to_owned(),\n'
        for minor, tag in releases.tags_by_minor
    )
    text = replace_span(
        text,
        match.span(),
        (match.group("start") + match_lines + match.group("end")),
    )

    cases_pattern = re.compile(
        r"(?P<start>^    #\[rstest\]\n)"
        r"(?:^    #\[case\(.*\)\]\n)+"
        r"(?P<end>^    fn test_get_cloud_provider_tag_from_kube_tag\()",
        re.MULTILINE,
    )
    cases = "".join(
        f'    #[case("v1.{minor}.0", "{tag}")]\n'
        for minor, tag in releases.tags_by_minor
    )
    cases += "".join(
        f'    #[case("{value}", "{releases.default_tag}")]\n'
        for value in ("v1.60.1", "v2.0.0", "invalid", "master")
    )
    cases_match = single_match(
        text,
        cases_pattern,
        "cloud-provider tag test case block",
    )
    text = replace_span(
        text,
        cases_match.span(),
        cases_match.group("start") + cases + cases_match.group("end"),
    )

    missing_defaults = set(IMAGE_TAG_SOURCES) - set(image_defaults)
    extra_defaults = set(image_defaults) - set(IMAGE_TAG_SOURCES)
    if missing_defaults or extra_defaults:
        raise ScriptError(
            "Image default fields do not match the configured sources: "
            f"missing={sorted(missing_defaults)}, extra={sorted(extra_defaults)}"
        )

    for field, tag in image_defaults.items():
        field_pattern = re.compile(
            rf'(?P<builder>    #\[builder\(default=")[^"]+'
            rf'(?P<middle>"\.to_owned\(\)\)\]\n    #\[pyo3\(default=")[^"]+'
            rf'(?P<end>"\.to_owned\(\)\)\]\n    pub {re.escape(field)}: String,)'
        )
        field_match = single_match(text, field_pattern, f"Rust default field {field}")
        replacement = (
            field_match.group("builder")
            + tag
            + field_match.group("middle")
            + tag
            + field_match.group("end")
        )
        text = replace_span(text, field_match.span(), replacement)

    return text


def rust_image_defaults(text: str) -> dict[str, str]:
    defaults = {}
    for field in IMAGE_TAG_SOURCES:
        pattern = re.compile(
            rf'    #\[builder\(default="(?P<builder>[^"]+)"\.to_owned\(\)\)\]\n'
            rf'    #\[pyo3\(default="(?P<pyo3>[^"]+)"\.to_owned\(\)\)\]\n'
            rf"    pub {re.escape(field)}: String,"
        )
        match = pattern.search(text)
        if match is None:
            raise ScriptError(f"Unable to read Rust default field {field}")
        if match.group("builder") != match.group("pyo3"):
            raise ScriptError(f"Builder and PyO3 defaults disagree for {field}")
        defaults[field] = match.group("builder")
    return defaults


def validate_repository(charts_file: Path, charts_root: Path, rust_file: Path) -> None:
    configured_versions = configured_chart_versions(charts_file.read_text())
    documents = load_chart_documents(charts_root)
    for chart, configured_version in configured_versions.items():
        vendored_version = documents[chart].chart.get("version")
        if vendored_version != configured_version:
            raise ScriptError(
                f"{chart} is configured at {configured_version} but vendored at "
                f"{vendored_version}"
            )

    chart_defaults = image_defaults_from_charts(documents)
    rust_defaults = rust_image_defaults(rust_file.read_text())
    if rust_defaults != chart_defaults:
        mismatches = [
            f"{field}: Rust={rust_defaults.get(field)}, chart={chart_defaults.get(field)}"
            for field in IMAGE_TAG_SOURCES
            if rust_defaults.get(field) != chart_defaults.get(field)
        ]
        raise ScriptError(
            "CSI image defaults are out of sync:\n" + "\n".join(mismatches)
        )


def run_chart_vendor(root: Path, charts_root: Path) -> None:
    try:
        subprocess.run(
            [
                "go",
                "run",
                "github.com/vexxhost/chart-vendor@latest",
                "--charts-root",
                str(charts_root),
            ],
            cwd=root,
            check=True,
        )
    except FileNotFoundError as exc:
        raise ScriptError("Unable to run chart-vendor: go was not found") from exc
    except subprocess.CalledProcessError as exc:
        raise ScriptError(
            f"chart-vendor failed with exit code {exc.returncode}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=RELEASE_REPOSITORY)
    parser.add_argument("--charts-file", type=Path, default=root / ".charts.yml")
    parser.add_argument(
        "--charts-root",
        type=Path,
        default=root / "magnum_cluster_api/charts",
    )
    parser.add_argument("--rust-file", type=Path, default=root / "src/magnum.rs")
    parser.add_argument("--self-test", action="store_true", help="run embedded tests")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the current repository without updating it",
    )
    args = parser.parse_args(argv or sys.argv[1:])

    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            CloudProviderOpenStackBumpTests
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    try:
        if args.check:
            validate_repository(args.charts_file, args.charts_root, args.rust_file)
            print("cloud-provider-openstack charts and image defaults are synchronized")
            return 0

        releases = latest_releases(args.repository)
        args.charts_file.write_text(
            update_chart_versions(args.charts_file.read_text(), releases.chart_versions)
        )
        run_chart_vendor(root, args.charts_root)

        documents = load_chart_documents(args.charts_root)
        image_defaults = image_defaults_from_charts(documents)
        args.rust_file.write_text(
            update_rust_source(
                args.rust_file.read_text(),
                releases,
                image_defaults,
            )
        )
        validate_repository(args.charts_file, args.charts_root, args.rust_file)
    except (OSError, ScriptError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        f"Updated cloud-provider-openstack from {args.repository}:\n"
        f"  default image tag: {releases.default_tag}"
    )
    for chart, version in releases.chart_versions.items():
        print(f"  {chart}: {version}")
    return 0


class CloudProviderOpenStackBumpTests(unittest.TestCase):
    def test_release_info_selects_latest_versions_independent_of_order(self) -> None:
        releases = release_info(
            ["v1.23.3", "ignored", "v1.22.2", "v1.23.4", "v2.0.0"],
            [
                "openstack-manila-csi-2.34.1",
                "v1.34.1",
                "openstack-cinder-csi-2.34.1",
                "openstack-cloud-controller-manager-2.36.0",
                "v1.35.0",
                "openstack-cinder-csi-2.35.0",
            ],
        )

        self.assertEqual(releases.default_tag, "v1.35.0")
        self.assertEqual(
            releases.tags_by_minor,
            ((22, "v1.22.2"), (23, "v1.23.4")),
        )
        self.assertEqual(
            releases.chart_versions,
            {
                "openstack-cloud-controller-manager": "2.36.0",
                "openstack-cinder-csi": "2.35.0",
                "openstack-manila-csi": "2.34.1",
            },
        )

    def test_update_chart_versions_updates_every_cpo_chart(self) -> None:
        source = dedent(
            """
            charts:
              - name: unrelated
                version: 1.0.0
              - name: openstack-cloud-controller-manager
                version: 2.34.0
              - name: openstack-cinder-csi
                version: 2.34.0
              - name: openstack-manila-csi
                version: 2.34.0
            """
        )
        versions = {chart: "2.35.0" for chart in CHART_NAMES}

        updated = update_chart_versions(source, versions)

        self.assertEqual(configured_chart_versions(updated), versions)
        self.assertIn("name: unrelated\n    version: 1.0.0", updated)

    def test_image_defaults_require_shared_sidecars_to_match(self) -> None:
        documents = self.chart_documents()
        documents[MANILA_CHART].values["controllerplugin"]["resizer"]["image"][
            "tag"
        ] = "v1.13.0"

        with self.assertRaisesRegex(ScriptError, "csi_resizer_tag"):
            image_defaults_from_charts(documents)

    def test_update_rust_source_is_complete_and_idempotent(self) -> None:
        releases = ReleaseInfo(
            default_tag="v1.35.0",
            tags_by_minor=((22, "v1.22.2"), (35, "v1.35.0")),
            chart_versions={chart: "2.35.0" for chart in CHART_NAMES},
        )
        defaults = image_defaults_from_charts(self.chart_documents())
        source = self.rust_source()

        updated = update_rust_source(source, releases, defaults)

        self.assertEqual(rust_image_defaults(updated), defaults)
        self.assertIn('(1, 35) => "v1.35.0".to_owned(),', updated)
        self.assertNotIn('(1, 23) => "v1.23.3".to_owned(),', updated)
        self.assertIn('#[case("invalid", "v1.35.0")]', updated)
        self.assertEqual(update_rust_source(updated, releases, defaults), updated)

    def test_update_rust_source_rejects_missing_image_field(self) -> None:
        releases = ReleaseInfo(
            default_tag="v1.35.0",
            tags_by_minor=((35, "v1.35.0"),),
            chart_versions={chart: "2.35.0" for chart in CHART_NAMES},
        )
        defaults = image_defaults_from_charts(self.chart_documents())
        source = self.rust_source().replace(
            "    pub csi_snapshotter_tag: String,",
            "    pub renamed_snapshotter_tag: String,",
        )

        with self.assertRaisesRegex(ScriptError, "csi_snapshotter_tag"):
            update_rust_source(source, releases, defaults)

    @staticmethod
    def chart_documents() -> dict[str, ChartDocuments]:
        cinder_values = {
            "csi": {
                "attacher": {"image": {"tag": "v4.10.0"}},
                "livenessprobe": {"image": {"tag": "v2.17.0"}},
                "nodeDriverRegistrar": {"image": {"tag": "v2.15.0"}},
                "provisioner": {"image": {"tag": "v5.3.0"}},
                "resizer": {"image": {"tag": "v1.14.0"}},
                "snapshotter": {"image": {"tag": "v8.4.0"}},
            }
        }
        manila_values = {
            "nodeplugin": {"registrar": {"image": {"tag": "v2.15.0"}}},
            "controllerplugin": {
                "provisioner": {"image": {"tag": "v5.3.0"}},
                "resizer": {"image": {"tag": "v1.14.0"}},
                "snapshotter": {"image": {"tag": "v8.4.0"}},
            },
        }
        return {
            "openstack-cloud-controller-manager": ChartDocuments(
                chart={"version": "2.35.0", "appVersion": "v1.35.0"},
                values={},
            ),
            CINDER_CHART: ChartDocuments(
                chart={"version": "2.35.0", "appVersion": "v1.35.0"},
                values=cinder_values,
            ),
            MANILA_CHART: ChartDocuments(
                chart={"version": "2.35.0", "appVersion": "v1.35.0"},
                values=manila_values,
            ),
        }

    @staticmethod
    def rust_source() -> str:
        fields = "\n\n".join(
            f'    #[builder(default="old".to_owned())]\n'
            f'    #[pyo3(default="old".to_owned())]\n'
            f"    pub {field}: String,"
            for field in IMAGE_TAG_SOURCES
        )
        return (
            dedent(
                """\
                impl ClusterLabels {
                    const DEFAULT_CLOUD_PROVIDER_TAG: &'static str = "v1.34.0";

                    fn get_cloud_provider_tag(&self) -> String {
                        match (version.major, version.minor) {
                            (1, 22) => "v1.22.1".to_owned(),
                            (1, 23) => "v1.23.3".to_owned(),
                            _ => Self::DEFAULT_CLOUD_PROVIDER_TAG.to_owned(),
                        }
                    }
                }

                    #[rstest]
                    #[case("v1.22.0", "v1.22.1")]
                    #[case("v1.23.0", "v1.23.3")]
                    #[case("invalid", "v1.34.0")]
                    fn test_get_cloud_provider_tag_from_kube_tag(
                        #[case] kube_tag: &str,
                    ) {}

                """
            )
            + fields
            + "\n"
        )


if __name__ == "__main__":
    sys.exit(main())
