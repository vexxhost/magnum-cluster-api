set -e

# Fetch current maintained Kubernetes versions
VERSIONS=$(curl -s https://endoflife.date/api/v1/products/kubernetes | jq -r '.result.releases[] | select(.isMaintained == true).latest.name' | sort -V)

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

# Update conformance workflow in place using awk
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
' .github/workflows/conformance.yml

# Get the latest stable version (last one in the sorted list)
LATEST_VERSION=$(echo "$VERSIONS" | tail -n 1)

echo "Updated Kubernetes versions in CI and conformance workflows to:"
echo "$VERSIONS"
