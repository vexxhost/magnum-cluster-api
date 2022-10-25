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


@click.command()
@click.option(
    "--operating-system",
    show_default=True,
    default="ubuntu-2004",
    type=click.Choice(["ubuntu-2004"]),
    help="Operating system to build image for",
)
@click.option(
    "--version",
    show_default=True,
    default="v1.25.3",
    help="Kubernetes version",
)
@click.option(
    "--image-builder-version",
    show_default=True,
    default="v0.1.13",
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
