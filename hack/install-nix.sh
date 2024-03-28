#!/bin/bash -xe

# Copyright (c) 2024 VEXXHOST, Inc.
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

# Install Nix
sh <(curl -L https://nixos.org/nix/install) --no-channel-add --daemon --daemon-user-count $(nproc)

# Add Flake support
cat <<EOF | sudo tee -a /etc/nix/nix.conf
show-trace = true
max-jobs = auto
trusted-users = root ${USER:-}
experimental-features = nix-command flakes
EOF
