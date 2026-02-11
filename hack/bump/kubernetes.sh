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

# Build the version list for YAML
VERSION_LINES=""
for version in $VERSIONS; do
    VERSION_LINES="${VERSION_LINES}          - ${version}\n"
done

# Update CI workflow in place using awk
awk -i inplace -v versions="$VERSION_LINES" '
/^[[:space:]]{8}kubernetes-version:[[:space:]]*$/ {
  print
  printf "%s", versions
  in_k8s = 1
  next
}
in_k8s && /^[[:space:]]{10}-[[:space:]]/ {
  # Skip old version lines
  next
}
in_k8s && !/^[[:space:]]{10}-[[:space:]]/ {
  in_k8s = 0
}
!in_k8s {
  print
}
' .github/workflows/ci.yml

# Get the latest stable version (last one in the sorted list)
LATEST_VERSION=$(echo "$VERSIONS" | tail -n 1)

echo "Updated Kubernetes versions in CI workflow to:"
echo "$VERSIONS"
