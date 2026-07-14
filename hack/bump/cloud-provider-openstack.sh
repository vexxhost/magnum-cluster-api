#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec uv run --no-project --script "${SCRIPT_DIR}/cloud-provider-openstack.py" "$@"
