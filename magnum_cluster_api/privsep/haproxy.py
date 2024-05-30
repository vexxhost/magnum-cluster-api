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

import os
import signal
import subprocess

from oslo_log import log as logging

import magnum_cluster_api.privsep
from magnum_cluster_api import conf

CONF = conf.CONF
LOG = logging.getLogger(__name__)


@magnum_cluster_api.privsep.haproxy_pctxt.entrypoint
def start(config_file):
    proc = subprocess.Popen(["haproxy", "-f", config_file])

    try:
        retcode = proc.wait(timeout=5)
        if retcode != 0:
            LOG.error("HAproxy failed to start")
    except subprocess.TimeoutExpired:
        LOG.info("HAproxy started successfully")

    return proc.pid


@magnum_cluster_api.privsep.haproxy_pctxt.entrypoint
def reload():
    """Reload HAproxy configuration"""

    with open(CONF.proxy.haproxy_pid_path, "r") as fd:
        pid = int(fd.read().strip())

    os.kill(pid, signal.SIGUSR2)
