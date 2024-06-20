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

# Versions to test
VENDIR_VERSION=${VENDIR_VERSION:-v0.40.0}

# Install `vendir` CLI
curl -Lo /tmp/vendir https://github.com/carvel-dev/vendir/releases/download/${VENDIR_VERSION}/vendir-linux-amd64
chmod +x /tmp/vendir
sudo mv /tmp/vendir /usr/local/bin/vendir
