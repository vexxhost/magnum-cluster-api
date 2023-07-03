# Copyright (c) 2023 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import getpass
import json
import os
import subprocess
import tarfile
import tempfile
import textwrap
import zlib
from pathlib import Path

import click
import requests

QEMU_PACKAGES = [
    "qemu-kvm",
    "libvirt-daemon-system",
    "libvirt-clients",
    "virtinst",
    "cpu-checker",
    "libguestfs-tools",
    "libosinfo-bin",
]


def validate_version(_, __, value):
    if not value.startswith("v"):
        raise click.BadParameter("Version should start with 'v'")
    return value


@click.command()
@click.option(
    "--operating-system",
    show_default=True,
    default="ubuntu-2204",
    type=click.Choice(["ubuntu-2004", "ubuntu-2204"]),
    help="Operating system to build image for",
)
@click.option(
    "--version",
    show_default=True,
    default="v1.27.3",
    callback=validate_version,
    help="Kubernetes version",
)
@click.option(
    "--image-builder-version",
    show_default=True,
    default="d37da2a",
    help="Image builder tag (or commit) to use for building image",
)
def main(operating_system, version, image_builder_version):
    ib_path = f"/tmp/image-builder-{image_builder_version}"
    output = f"{operating_system}-kube-{version}"

    target = f"{ib_path}/images/capi/output/{output}/{output}"
    if os.path.exists(target):
        print(f"Image already exists: {target}")
        return

    click.echo("- Install QEMU packages")
    subprocess.run(
        ["sudo", "/usr/bin/apt", "install", "-y"] + QEMU_PACKAGES, check=True
    )

    click.echo("- Add current user to KVM group")
    subprocess.run(
        ["sudo", "/usr/sbin/usermod", "-a", "-G", "kvm", getpass.getuser()], check=True
    )

    click.echo("- Update permissions for the KVM device")
    subprocess.run(["sudo", "/bin/chown", "root:kvm", "/dev/kvm"], check=True)

    # Setup our stream decompressor
    dec = zlib.decompressobj(32 + zlib.MAX_WBITS)

    click.echo("- Download image-builder")
    path = f"{ib_path}.tar"
    with requests.get(
        f"https://github.com/kubernetes-sigs/image-builder/tarball/{image_builder_version}",
        stream=True,
    ) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                rv = dec.decompress(chunk)
                if rv:
                    f.write(rv)

    click.echo("- Extract image-builder")
    with tarfile.open(path) as tar:
        members = []
        for member in tar.getmembers():
            p = Path(member.path)
            member.path = p.relative_to(*p.parts[:1])
            members.append(member)

        tar.extractall(ib_path, members=members)

    click.echo("- Create customization file")
    kubernetes_series = ".".join(version.split(".")[0:2])
    customization = {
        "kubernetes_deb_version": f"{version.replace('v', '')}-00",
        "kubernetes_semver": f"{version}",
        "kubernetes_series": f"{kubernetes_series}",
    }

    # NOTE(mnaser): We use the latest tested daily ISO for Ubuntu 22.04 in order
    #               to avoid a lengthy upgrade process.
    if operating_system == "ubuntu-2204":
        iso = "jammy-live-server-amd64.iso"

        customization[
            "iso_url"
        ] = f"http://cdimage.ubuntu.com/ubuntu-server/jammy/daily-live/current/{iso}"

        # Get the SHA256 sum for the ISO
        r = requests.get(
            "http://cdimage.ubuntu.com/ubuntu-server/jammy/daily-live/current/SHA256SUMS"
        )
        r.raise_for_status()
        for line in r.text.splitlines():
            if iso in line:
                customization["iso_checksum"] = line.split()[0]
                break

        # Assert that we have the checksum
        assert "iso_checksum" in customization

    with tempfile.NamedTemporaryFile(suffix=".json") as fp:
        fp.write(json.dumps(customization).encode("utf-8"))
        fp.flush()

        click.echo("- Build image")
        subprocess.run(
            [
                "/usr/bin/newgrp",
                "kvm",
            ],
            input=textwrap.dedent(
                f"""\
                /usr/bin/make \
                -C \
                {ib_path}/images/capi \
                build-qemu-{operating_system}
            """
            ).encode("utf-8"),
            env={
                **os.environ,
                **{
                    "PACKER_VAR_FILES": fp.name,
                },
            },
        )
