#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "PyGithub>=2.6,<3",
#   "PyYAML>=6.0.2,<7",
# ]
# ///

from __future__ import annotations

import argparse
import os
import re
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml
from github import Auth, Github
from github.GithubException import GithubException, UnknownObjectException

RELEASE_REPOSITORY = "vexxhost/capo-image-elements"
IMAGE_PREFIX = "ubuntu-22.04"
CANARY_IMAGE_PREFIXES = ("ubuntu-24.04",)

BASE_JOB_NAME = "magnum-cluster-api-hydrophone"
PROJECT_TEMPLATE_NAME = f"{BASE_JOB_NAME}-jobs"
VERSIONED_JOB_PREFIX = f"{BASE_JOB_NAME}-v"
NETWORK_DRIVERS = ("calico", "cilium")
IMAGE_URL = (
    "https://github.com/vexxhost/capo-image-elements/releases/download/"
    "{{ image_release }}/{{ image_prefix }}-{{ kube_tag }}.qcow2"
)

KUBERNETES_IMAGE_RE = re.compile(r"^.+-v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)\.qcow2$")


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    tag_name: str
    name: str
    image_prefix: str
    versions: tuple[str, ...]
    assets: tuple[str, ...]


class IndentedDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
        return super().increase_indent(flow, False)


def semver_key(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def latest_release(repository: str, image_prefix: str) -> Release:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    github = Github(auth=Auth.Token(token)) if token else Github()

    try:
        repo = github.get_repo(repository)
        release = repo.get_latest_release()
        tag_name = release.tag_name
        assets = [asset.name for asset in release.get_assets()]

        if not tag_name:
            raise ScriptError(f"Latest release for {repository} has no tag name")

        return Release(
            tag_name=tag_name,
            name=release.name or tag_name,
            image_prefix=image_prefix,
            versions=versions_from_assets(tag_name, assets, image_prefix),
            assets=tuple(assets),
        )
    except UnknownObjectException as exc:
        raise ScriptError(
            f"Unable to find the latest release for {repository}"
        ) from exc
    except GithubException as exc:
        message = str(exc)
        if isinstance(exc.data, dict) and exc.data.get("message"):
            message = str(exc.data["message"])
        raise ScriptError(
            f"GitHub API request failed for {repository}: {message}"
        ) from exc
    finally:
        github.close()


def versions_from_assets(
    tag_name: str,
    assets: list[str],
    image_prefix: str,
) -> tuple[str, ...]:
    release_versions = set()
    image_versions = set()
    image_re = re.compile(
        rf"^{re.escape(image_prefix)}-v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)\.qcow2$"
    )

    for asset in assets:
        release_match = KUBERNETES_IMAGE_RE.match(asset)
        if release_match:
            release_versions.add(release_match.group("version"))

        image_match = image_re.match(asset)
        if image_match:
            image_versions.add(image_match.group("version"))

    if not image_versions:
        raise ScriptError(f"Release {tag_name} has no {image_prefix} Kubernetes images")

    missing_versions = sorted(release_versions - image_versions, key=semver_key)
    if missing_versions:
        versions = "\n".join(f"  v{version}" for version in missing_versions)
        raise ScriptError(
            f"Release {tag_name} has Kubernetes versions without "
            f"{image_prefix} images:\n{versions}"
        )

    return tuple(sorted(image_versions, key=semver_key))


def dump_yaml(path: Path, document: list[Any]) -> None:
    path.write_text(
        yaml.dump(
            document,
            Dumper=IndentedDumper,
            sort_keys=False,
            width=4096,
        )
    )


def job_name(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None

    job = entry.get("job")
    if not isinstance(job, dict):
        return None

    name = job.get("name")
    return name if isinstance(name, str) else None


def hydrophone_jobs(release: Release) -> list[dict[str, Any]]:
    generated_jobs = [
        f"{VERSIONED_JOB_PREFIX}{version}-{network_driver}"
        for version in release.versions
        for network_driver in NETWORK_DRIVERS
    ]
    latest_version = release.versions[-1]
    canary_prefixes = [
        prefix for prefix in CANARY_IMAGE_PREFIXES if prefix != release.image_prefix
    ]
    canary_jobs = [
        f"{BASE_JOB_NAME}-{prefix}-v{latest_version}-{network_driver}"
        for prefix in canary_prefixes
        for network_driver in NETWORK_DRIVERS
    ]
    jobs = [
        {
            "project-template": {
                "name": PROJECT_TEMPLATE_NAME,
                "check": {"jobs": list(generated_jobs) + list(canary_jobs)},
                "gate": {"jobs": list(generated_jobs) + list(canary_jobs)},
            }
        },
        {
            "job": {
                "name": BASE_JOB_NAME,
                "parent": "magnum-cluster-api-devstack",
                "abstract": True,
                "pre-run": "zuul.d/playbooks/hydrophone/pre.yml",
                "run": "zuul.d/playbooks/hydrophone/run.yml",
                "post-run": "zuul.d/playbooks/hydrophone/post.yml",
                "vars": {
                    "image_prefix": release.image_prefix,
                    "image_url": IMAGE_URL,
                    "devstack_localrc": {
                        "MAGNUM_GUEST_IMAGE_URL": "{{ image_url }}",
                    },
                },
            }
        },
    ]

    for version in release.versions:
        jobs.append(
            {
                "job": {
                    "name": f"{VERSIONED_JOB_PREFIX}{version}",
                    "parent": BASE_JOB_NAME,
                    "vars": {
                        "image_release": release.tag_name,
                        "kube_tag": f"v{version}",
                    },
                }
            }
        )

        for network_driver in NETWORK_DRIVERS:
            jobs.append(
                {
                    "job": {
                        "name": f"{VERSIONED_JOB_PREFIX}{version}-{network_driver}",
                        "parent": f"{VERSIONED_JOB_PREFIX}{version}",
                        "vars": {
                            "network_driver": network_driver,
                        },
                    }
                }
            )

    for prefix in canary_prefixes:
        canary_versions = set(
            versions_from_assets(release.tag_name, list(release.assets), prefix)
        )
        if latest_version not in canary_versions:
            raise ScriptError(
                f"Release {release.tag_name} has no {prefix} image "
                f"for v{latest_version}"
            )

        jobs.append(
            {
                "job": {
                    "name": f"{BASE_JOB_NAME}-{prefix}-v{latest_version}",
                    "parent": f"{VERSIONED_JOB_PREFIX}{latest_version}",
                    "vars": {
                        "image_prefix": prefix,
                    },
                }
            }
        )

        for network_driver in NETWORK_DRIVERS:
            jobs.append(
                {
                    "job": {
                        "name": (
                            f"{BASE_JOB_NAME}-{prefix}-v{latest_version}-"
                            f"{network_driver}"
                        ),
                        "parent": f"{BASE_JOB_NAME}-{prefix}-v{latest_version}",
                        "vars": {
                            "network_driver": network_driver,
                        },
                    }
                }
            )

    return jobs


def prune_jobs_text(text: str) -> str:
    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in text.splitlines(keepends=True):
        if line.startswith("- job:") and current_block:
            blocks.append(current_block)
            current_block = []
        current_block.append(line)

    if current_block:
        blocks.append(current_block)

    kept_blocks = []
    for block in blocks:
        name = None
        for line in block:
            if line.startswith("    name: "):
                name = line.split(":", 1)[1].strip().strip("\"'")
                break

        if name == BASE_JOB_NAME or (
            name is not None and name.startswith(f"{BASE_JOB_NAME}-")
        ):
            continue
        kept_blocks.append("".join(block))

    return "".join(kept_blocks).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=RELEASE_REPOSITORY)
    parser.add_argument("--image-prefix", default=IMAGE_PREFIX)
    parser.add_argument("--jobs-file", type=Path, default=root / "zuul.d/jobs.yaml")
    parser.add_argument(
        "--hydrophone-jobs-file",
        type=Path,
        default=root / "zuul.d/hydrophone-jobs.yaml",
    )
    parser.add_argument(
        "--project-file", type=Path, default=root / "zuul.d/project.yaml"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run embedded unit tests"
    )
    args = parser.parse_args(argv or sys.argv[1:])

    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(KubernetesBumpTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    try:
        release = latest_release(args.repository, args.image_prefix)
        args.jobs_file.write_text(prune_jobs_text(args.jobs_file.read_text()))
        dump_yaml(args.hydrophone_jobs_file, hydrophone_jobs(release))
        dump_yaml(
            args.project_file,
            [{"project": {"templates": [PROJECT_TEMPLATE_NAME]}}],
        )
    except ScriptError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        f"Updated Kubernetes versions in Zuul jobs from "
        f"{args.repository} {release.name} ({release.tag_name}):"
    )
    for version in release.versions:
        print(f"  v{version}")

    return 0


class KubernetesBumpTests(unittest.TestCase):
    def test_versions_from_assets_selects_all_image_versions(self) -> None:
        assets = [
            "debian-13-v1.33.12.qcow2",
            "debian-13-v1.34.8.qcow2",
            "ubuntu-22.04-v1.34.8.qcow2",
            "ubuntu-22.04-v1.33.12.qcow2",
            "ubuntu-24.04-v1.33.12.qcow2",
            "ubuntu-24.04-v1.34.8.qcow2",
        ]

        self.assertEqual(
            versions_from_assets("2026.05-7", assets, "ubuntu-22.04"),
            ("1.33.12", "1.34.8"),
        )

    def test_versions_from_assets_requires_prefix_for_every_release_version(
        self,
    ) -> None:
        assets = [
            "debian-13-v1.33.12.qcow2",
            "ubuntu-22.04-v1.34.8.qcow2",
        ]

        with self.assertRaisesRegex(ScriptError, "v1.33.12"):
            versions_from_assets("2026.05-7", assets, "ubuntu-22.04")

    def test_hydrophone_jobs_include_template_base_release_and_network_jobs(
        self,
    ) -> None:
        release = Release(
            tag_name="2026.05-7",
            name="2026.05-7",
            image_prefix="ubuntu-22.04",
            versions=("1.33.12",),
            assets=(
                "ubuntu-22.04-v1.33.12.qcow2",
                "ubuntu-24.04-v1.33.12.qcow2",
            ),
        )
        document = hydrophone_jobs(release)

        template = document[0]["project-template"]
        self.assertEqual(template["name"], PROJECT_TEMPLATE_NAME)
        self.assertEqual(
            template["check"]["jobs"],
            [
                "magnum-cluster-api-hydrophone-v1.33.12-calico",
                "magnum-cluster-api-hydrophone-v1.33.12-cilium",
                "magnum-cluster-api-hydrophone-ubuntu-24.04-v1.33.12-calico",
                "magnum-cluster-api-hydrophone-ubuntu-24.04-v1.33.12-cilium",
            ],
        )
        self.assertEqual(template["gate"]["jobs"], template["check"]["jobs"])
        rendered = yaml.dump(
            document,
            Dumper=IndentedDumper,
            sort_keys=False,
            width=4096,
        )
        self.assertNotIn("&id", rendered)
        self.assertNotIn("*id", rendered)

        self.assertEqual(job_name(document[1]), BASE_JOB_NAME)
        self.assertIn("{{ image_release }}", document[1]["job"]["vars"]["image_url"])
        self.assertIn("{{ image_prefix }}", document[1]["job"]["vars"]["image_url"])
        self.assertEqual(document[1]["job"]["vars"]["image_prefix"], "ubuntu-22.04")
        self.assertEqual(
            [job_name(entry) for entry in document[2:]],
            [
                "magnum-cluster-api-hydrophone-v1.33.12",
                "magnum-cluster-api-hydrophone-v1.33.12-calico",
                "magnum-cluster-api-hydrophone-v1.33.12-cilium",
                "magnum-cluster-api-hydrophone-ubuntu-24.04-v1.33.12",
                "magnum-cluster-api-hydrophone-ubuntu-24.04-v1.33.12-calico",
                "magnum-cluster-api-hydrophone-ubuntu-24.04-v1.33.12-cilium",
            ],
        )
        self.assertEqual(document[2]["job"]["vars"]["image_release"], "2026.05-7")
        self.assertEqual(document[5]["job"]["vars"]["image_prefix"], "ubuntu-24.04")

    def test_prune_jobs_text_preserves_non_hydrophone_job_format(self) -> None:
        text = dedent(
            """
            - job:
                name: magnum-cluster-api-devstack
                required-projects:
                  - opendev.org/openstack/barbican
                  - opendev.org/openstack/magnum
                nodeset:
                  nodes:
                    - name: controller
                      label: ubuntu-noble-16

            - job:
                name: magnum-cluster-api-hydrophone
            - job:
                name: magnum-cluster-api-hydrophone-v1.32.9
            - job:
                name: magnum-cluster-api-hydrophone-ubuntu-24.04-v1.32.9
            """
        )
        expected = dedent(
            """
            - job:
                name: magnum-cluster-api-devstack
                required-projects:
                  - opendev.org/openstack/barbican
                  - opendev.org/openstack/magnum
                nodeset:
                  nodes:
                    - name: controller
                      label: ubuntu-noble-16
            """
        )

        self.assertEqual(prune_jobs_text(text), expected)

    def test_project_file_uses_hydrophone_template_only(self) -> None:
        document = [{"project": {"templates": [PROJECT_TEMPLATE_NAME]}}]

        self.assertEqual(
            yaml.dump(
                document,
                Dumper=IndentedDumper,
                sort_keys=False,
                width=4096,
            ),
            dedent(
                """
                - project:
                    templates:
                      - magnum-cluster-api-hydrophone-jobs
                """
            ).lstrip(),
        )


if __name__ == "__main__":
    sys.exit(main())
