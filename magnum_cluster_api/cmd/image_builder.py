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

# NOTE(mnaser): We use this file to gate if we do build new images or not,
#               so we will simply keep increasing the following placeholder,
#               feel free to keep counting up.
#
#               Image build count: 1

import getpass
import json
import os
import subprocess
import tarfile
import tempfile
import textwrap
import zlib
from os.path import expanduser
from pathlib import Path

import click
import requests

QEMU_PACKAGES = [
    "qemu-kvm",
    "qemu-utils",
    "mkisofs",
]


def validate_version(_, __, value):
    if not value.startswith("v"):
        raise click.BadParameter("Version should start with 'v'")
    return value


@click.command()
@click.pass_context
@click.option(
    "--operating-system",
    show_default=True,
    default="ubuntu-2204",
    type=click.Choice(
        ["ubuntu-2004", "ubuntu-2204", "flatcar", "rockylinux-8", "rockylinux-9"]
    ),
    help="Operating system to build image for",
    prompt="Operating system to build image for",
)
@click.option(
    "--version",
    show_default=True,
    default="v1.29.5",
    callback=validate_version,
    help="Kubernetes version",
)
@click.option(
    "--image-builder-version",
    show_default=True,
    default="v0.1.31",
    help="Image builder tag (or commit) to use for building image",
)
@click.option(
    "--extra-ansible-user-vars",
    show_default=True,
    default="",
    help="Extra user defined variables to set in image-builder ansible_user_vars",
)
@click.option(
    "--node-custom-roles-pre",
    show_default=True,
    default="",
    help="Custom pre-roles to run in image-builder",
)
def main(
    ctx: click.Context,
    operating_system,
    version,
    image_builder_version,
    extra_ansible_user_vars,
    node_custom_roles_pre,
):
    ib_path = f"/tmp/image-builder-{image_builder_version}"
    output_path = f"{ib_path}/images/capi/output"

    # Scan the entire output directory recursively and stop if there is any file
    # at all
    for root, dirs, files in os.walk(output_path):
        if files:
            message = (
                "There are files in the output directory which will cause the build to fail. "
                "Please remove them before continuing.\n"
            )
            for file in files:
                message += f"- {root}/{file}\n"

            ctx.fail(message)

    click.echo("- Update apt")
    subprocess.run(
        ["sudo", "/usr/bin/apt-get", "update", "-y"],
        check=True,
    )

    click.echo("- Install QEMU packages")
    subprocess.run(
        ["sudo", "/usr/bin/apt", "install", "--no-install-recommends", "-y"]
        + QEMU_PACKAGES,
        check=True,
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
        "kubernetes_deb_version": f"{version.replace('v', '')}-1.1",
        "kubernetes_rpm_version": f"{version.replace('v', '')}",
        "kubernetes_semver": f"{version}",
        "kubernetes_series": f"{kubernetes_series}",
        # https://github.com/flatcar/Flatcar/issues/823
        "ansible_user_vars": f"oem_id=openstack {extra_ansible_user_vars}",
        "node_custom_roles_pre": f"{node_custom_roles_pre}",
    }

    # NOTE(mnaser): Inside our CI, we use a local image in order speed up the
    #               process, so we will not download the image from the internet.
    if os.environ.get("CI") == "true":
        if operating_system == "ubuntu-2204":
            customization["iso_checksum"] = (
                "https://static.atmosphere.dev/ubuntu/jammy/20240605.1/SHA256SUMS"
            )
            customization["iso_url"] = (
                "https://static.atmosphere.dev/ubuntu/jammy/20240605.1/jammy-server-cloudimg-amd64.img"
            )
        elif operating_system == "rockylinux-8":
            customization["iso_checksum"] = (
                "https://static.atmosphere.dev/rocky/8/images/x86_64/CHECKSUM"
            )
            customization["iso_url"] = (
                "https://static.atmosphere.dev/rocky/8/images/x86_64/Rocky-8-GenericCloud-Base.latest.x86_64.qcow2"
            )
        elif operating_system == "rockylinux-9":
            customization["iso_checksum"] = (
                "https://static.atmosphere.dev/rocky/9/images/x86_64/CHECKSUM"
            )
            customization["iso_url"] = (
                "https://static.atmosphere.dev/rocky/9/images/x86_64/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2"
            )

    # NOTE(mnaser): Let's set number of CPUs to equal the number of CPUs on the
    #               host to speed up the build process.
    customization["cpus"] = str(os.cpu_count())

    # NOTE(mnaser): We set the memory of the VM to 50% of the total memory
    #               of the system.
    with open("/proc/meminfo", "r") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                total_memory_kb = int(line.split()[1])
                break
    total_memory_mb = total_memory_kb / 1024
    customization["memory"] = str(int(total_memory_mb * 0.5))

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
                build-qemu-{operating_system}-cloudimg
            """
            ).encode("utf-8"),
            env={
                **os.environ,
                **{
                    "PATH": f"{expanduser('~/.local/bin')}:{os.environ['PATH']}",
                    "PACKER_VAR_FILES": fp.name,
                },
            },
        )

    # Try and detect the target image path since it can be different depending
    # on the operating system, so we scan the output directory for the file
    # that matches the pattern.
    target = None
    for root, dirs, files in os.walk(output_path):
        if len(files) > 1:
            ctx.fail(f"Unexpected number of files in {root}")
        if files:
            target = f"{root}/{files[0]}"

    if target is None:
        ctx.fail("Unable to detect target image")

    # Copy from the target to the current working directory
    os.rename(target, f"{operating_system}-kube-{version}.qcow2")
