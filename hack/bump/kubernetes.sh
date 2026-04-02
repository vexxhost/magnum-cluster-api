set -euo pipefail

# Fetch Kubernetes versions from the latest capo-image-elements release (Ubuntu images).
TAG_NAME=$(
  gh release list --repo vexxhost/capo-image-elements \
    --limit 10 \
    --exclude-pre-releases \
    --exclude-drafts \
    --json tagName,isLatest \
    --jq '.[] | select(.isLatest == true) | .tagName'
)

ASSETS=$(
  gh release view "$TAG_NAME" --repo vexxhost/capo-image-elements \
    --json assets \
    --jq '.assets[].name'
)

VERSIONS=$(
  echo "$ASSETS" \
    | jq -Rr 'select(test("^ubuntu-22\\.04-v[0-9]+\\.[0-9]+\\.[0-9]+\\.qcow2$"))' \
    | sed -E 's/^ubuntu-22\.04-v([0-9]+\.[0-9]+\.[0-9]+)\.qcow2$/\1/' \
    | sort -V
)

SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
JOBS_FILE="${SCRIPT_DIR}/zuul.d/jobs.yaml"
PROJECT_FILE="${SCRIPT_DIR}/zuul.d/project.yaml"

# --- Update zuul.d/jobs.yaml ---
# Remove all existing hydrophone version jobs (keep everything up to and
# including the abstract hydrophone job).
awk '
/^- job:/ { pending = $0; next }
pending && /name: magnum-cluster-api-hydrophone-v/ {
  # This is a versioned hydrophone job — drop it
  pending = ""; skip = 1; next
}
pending { if (!skip) print pending; pending = ""; skip = 0 }
skip && /^- job:/ { skip = 0; pending = $0; next }
skip && /^[^ ]/ { skip = 0 }
!skip { print }
END { if (pending != "") print pending }
' "$JOBS_FILE" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' > "${JOBS_FILE}.tmp"

# Append new versioned hydrophone jobs
{
  for version in $VERSIONS; do
    cat <<EOF

- job:
    name: magnum-cluster-api-hydrophone-v${version}
    parent: magnum-cluster-api-hydrophone
    vars:
      kube_tag: v${version}

- job:
    name: magnum-cluster-api-hydrophone-v${version}-calico
    parent: magnum-cluster-api-hydrophone-v${version}
    vars:
      network_driver: calico

- job:
    name: magnum-cluster-api-hydrophone-v${version}-cilium
    parent: magnum-cluster-api-hydrophone-v${version}
    vars:
      network_driver: cilium
EOF
  done
} >> "${JOBS_FILE}.tmp"

mv "${JOBS_FILE}.tmp" "$JOBS_FILE"

# --- Update zuul.d/project.yaml ---
# Remove existing hydrophone version job references
sed -i '/magnum-cluster-api-hydrophone-v/d' "$PROJECT_FILE"

# Build replacement lines
HYDROPHONE_JOBS=""
for version in $VERSIONS; do
  HYDROPHONE_JOBS="${HYDROPHONE_JOBS}        - magnum-cluster-api-hydrophone-v${version}-calico\n"
  HYDROPHONE_JOBS="${HYDROPHONE_JOBS}        - magnum-cluster-api-hydrophone-v${version}-cilium\n"
done

# Insert hydrophone jobs at the end of each jobs: list. After removing
# hydrophone lines, each "jobs:" block ends with non-hydrophone entries
# followed by a non-list line (e.g. "    gate:" or EOF). We detect the
# transition and insert before it.
awk -v jobs="$HYDROPHONE_JOBS" '
in_jobs && !/^[[:space:]]*- / {
  printf "%s", jobs
  in_jobs = 0
}
/^[[:space:]]+jobs:/ { in_jobs = 1 }
{ print }
END { if (in_jobs) printf "%s", jobs }
' "$PROJECT_FILE" > "${PROJECT_FILE}.tmp"

mv "${PROJECT_FILE}.tmp" "$PROJECT_FILE"

echo "Updated Kubernetes versions in Zuul jobs to:"
echo "$VERSIONS"
