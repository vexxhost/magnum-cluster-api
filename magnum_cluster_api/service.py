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

from oslo_config import cfg
from oslo_context import context
from oslo_service import service

CONF = cfg.CONF


class Service(service.Service):
    def __init__(self, manager):
        super(Service, self).__init__()
        self.manager = manager()

    def start(self):
        self.tg.add_dynamic_timer(self.periodic_tasks)

    def periodic_tasks(self, raise_on_error=False):
        ctxt = context.get_admin_context()
        return self.manager.periodic_tasks(ctxt, raise_on_error=raise_on_error)


# NOTE: the global launcher is to maintain the existing
#       functionality of calling service.serve +
#       service.wait
_launcher = None


def serve(server, workers=None):
    global _launcher
    if _launcher:
        raise RuntimeError("serve() can only be called once")

    _launcher = service.launch(CONF, server, workers=workers, restart_method="mutate")


def wait():
    _launcher.wait()
