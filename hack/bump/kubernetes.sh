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

# Update Zuul jobs.yaml with new versions
echo "Updating Zuul jobs.yaml with Kubernetes versions..."

# Create a temporary file with the new job definitions
TEMP_JOBS=$(mktemp)

# Generate job definitions for each version
for version in $VERSIONS; do
    cat >> "$TEMP_JOBS" << EOF

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

# Replace the version-specific jobs in jobs.yaml
# Keep everything before the first version-specific job, then append new jobs
awk -v new_jobs="$(cat $TEMP_JOBS)" '
BEGIN { in_version_jobs = 0 }
/^- job:$/ {
    getline
    if ($0 ~ /name: magnum-cluster-api-hydrophone-v[0-9]/) {
        # Found a version-specific job, start skipping
        in_version_jobs = 1
        next
    } else {
        # Not a version job, print the job marker and the name line
        print "- job:"
        print
        next
    }
}
in_version_jobs && /^- job:$/ {
    # Check if this is still a version-specific job
    getline
    if ($0 !~ /name: magnum-cluster-api-hydrophone-v[0-9]/) {
        # End of version-specific jobs, print new jobs and resume
        print new_jobs
        in_version_jobs = 0
        print "- job:"
        print
    }
    # Otherwise keep skipping
    next
}
!in_version_jobs {
    print
}
END {
    # If we ended while still in version jobs, append new jobs at the end
    if (in_version_jobs) {
        print new_jobs
    }
}
' zuul.d/jobs.yaml > zuul.d/jobs.yaml.tmp && mv zuul.d/jobs.yaml.tmp zuul.d/jobs.yaml

rm "$TEMP_JOBS"

# Update Zuul project.yaml with new job names
echo "Updating Zuul project.yaml with job names..."

# Generate job list for project.yaml
ZUUL_JOBS=""
for version in $VERSIONS; do
    ZUUL_JOBS="${ZUUL_JOBS}        - magnum-cluster-api-hydrophone-v${version}-calico\n"
    ZUUL_JOBS="${ZUUL_JOBS}        - magnum-cluster-api-hydrophone-v${version}-cilium\n"
done

# Update project.yaml check section
awk -i inplace -v jobs="$ZUUL_JOBS" '
/^[[:space:]]{4}check:[[:space:]]*$/ {
    print
    print "      jobs:"
    print "        - magnum-cluster-api-tox-functional"
    print "        - magnum-cluster-api-tox-unit"
    printf "%s", jobs
    in_check = 1
    next
}
in_check && /^[[:space:]]{4}gate:[[:space:]]*$/ {
    in_check = 0
    print
    print "      jobs:"
    print "        - magnum-cluster-api-tox-functional"
    print "        - magnum-cluster-api-tox-unit"
    printf "%s", jobs
    in_gate = 1
    next
}
in_check || in_gate {
    if (/^[[:space:]]{4}[a-z]/ || /^[[:space:]]{0,3}[a-z]/) {
        # End of jobs section
        in_check = 0
        in_gate = 0
        print
    }
    # Skip old job lines
    next
}
!/^[[:space:]]{6}jobs:[[:space:]]*$/ && !/^[[:space:]]{8}-[[:space:]]/ {
    print
}
' zuul.d/project.yaml

# Get the latest stable version (last one in the sorted list)
LATEST_VERSION=$(echo "$VERSIONS" | tail -n 1)

echo "Updated Kubernetes versions in CI, conformance workflows, and Zuul to:"
echo "$VERSIONS"
