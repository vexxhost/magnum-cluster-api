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

import pytest
from magnum.common import context as magnum_context


@pytest.fixture
def context():
    return magnum_context.RequestContext(
        auth_token_info={
            "token": {"project": {"id": "fake_project"}, "user": {"id": "fake_user"}}
        },
        project_id="fake_project",
        user_id="fake_user",
        is_admin=False,
    )
