set -euo pipefail

FILE=${1:-src/magnum.rs}

# Build block with 12 spaces indentation, sorted by minor asc.
# We join with literal "\n" so awk can turn it into real newlines.
BLOCK=$(
  gh api repos/kubernetes/cloud-provider-openstack/tags --paginate \
  | jq -r '
      [ .[].name
        | select(test("^v1\\.[0-9]+\\.[0-9]+$"))
        | capture("^v(?<major>1)\\.(?<minor>\\d+)\\.(?<patch>\\d+)$")
        | .minor |= tonumber
        | .patch |= tonumber
      ]
      | map(select(.minor >= 22))
      | group_by(.minor)
      | map(max_by(.patch))
      | sort_by(.minor)
      | map({("1."+(.minor|tostring)): ("v"+.major+"."+(.minor|tostring)+"."+(.patch|tostring))})
      | add
      | to_entries
      | sort_by((.key|split(".")[1]|tonumber))
      | map("            (" + (.key|split(".")[0]) + ", " + (.key|split(".")[1]) + ") => \"" + .value + "\".to_owned(),")
      | join("\\n")
  '
)

# In-place replace contents of the match block using awk.
awk -i inplace -v block="$BLOCK" '
function print_block() {
  tmp = block
  gsub(/\\n/, "\n", tmp)   # turn literal \n into real newlines
  printf "%s\n", tmp
}
# Detect the start of the match block
/^        match \(version\.major, version\.minor\) \{$/ {
  print            # keep the opening line
  in_block = 1
  printed = 0
  next
}
# Detect the default case which ends the block
in_block && /^            _ => Self::DEFAULT_CLOUD_PROVIDER_TAG/ {
  if (!printed) { print_block(); printed = 1 }
  print            # keep the default case
  in_block = 0
  next
}
# Skip old lines inside the block
in_block { next }

# Everything else prints as-is
{ print }
' "$FILE"

BLOCK=$(
  gh api repos/kubernetes/cloud-provider-openstack/tags --paginate \
  | jq -r '
      [ .[].name
        | select(test("^v1\\.[0-9]+\\.[0-9]+$"))
        | capture("^v(?<major>1)\\.(?<minor>\\d+)\\.(?<patch>\\d+)$")
        | .minor |= tonumber
        | .patch |= tonumber
      ]
      | map(select(.minor >= 22))
      | group_by(.minor)
      | map(max_by(.patch))
      | sort_by(.minor)
      | map({("v1."+(.minor|tostring)): ("v"+.major+"."+(.minor|tostring)+"."+(.patch|tostring))})
      | add
      | to_entries
      | sort_by((.key|split(".")[1]|tonumber))
      | map("    #[case(\"" + (.key) + ".0\", \"" + (.value) + "\")]")
      | join("\\n")
  '
)


# Latest version of cluster-provider-openstack
CPO_VERSION=$(gh release list \
    --repo kubernetes/cloud-provider-openstack \
    --json tagName \
    --limit 1 \
    --jq '
        [ .[]
          | select(.tagName | startswith("v"))
        ]
        | first
        | .tagName
    ')
sed -i "s/const DEFAULT_CLOUD_PROVIDER_TAG: &'static str = \".*\";/const DEFAULT_CLOUD_PROVIDER_TAG: \\&'static str = \"$CPO_VERSION\";/" "$FILE"

# In-place replace test cases for test_get_cloud_provider_tag_from_kube_tag using awk.
awk -i inplace -v block="$BLOCK" -v default_tag="$CPO_VERSION" '
function print_block() {
  tmp = block
  gsub(/\\n/, "\n", tmp)   # turn literal \n into real newlines
  printf "%s\n", tmp
  # Add test cases for invalid versions - use the default tag variable
  print "    #[case(\"v1.60.1\", \"" default_tag "\")]"
  print "    #[case(\"v2.0.0\", \"" default_tag "\")]"
  print "    #[case(\"invalid\", \"" default_tag "\")]"
  print "    #[case(\"master\", \"" default_tag "\")]"
}

# Track if we are looking for the target function
/^    #\[rstest\]$/ {
  # Found an rstest attribute
  rstest_line = NR
  print
  next
}

# Look for case lines immediately after rstest
NR == rstest_line + 1 && /^    #\[case\(/ {
  # Start collecting test cases
  in_cases = 1
  case_buffer[0] = $0
  case_count = 1
  next
}

# Continue collecting case lines
in_cases && /^    #\[case\(/ {
  case_buffer[case_count++] = $0
  next
}

# Hit the function declaration after cases
in_cases && /^    fn test_get_cloud_provider_tag_from_kube_tag/ {
  # This is our target - replace the cases
  print_block()
  in_cases = 0
  delete case_buffer
  case_count = 0
  rstest_line = 0
  print  # Print the function declaration
  next
}

# Hit something else after cases - not our target
in_cases && !/^    #\[case\(/ {
  # Not our target, print buffered cases
  for (i = 0; i < case_count; i++) {
    print case_buffer[i]
  }
  in_cases = 0
  delete case_buffer
  case_count = 0
  rstest_line = 0
  print  # Print current line
  next
}

# Everything else prints as-is
{ print }
' "$FILE"

echo "Updated $FILE"

CHART_VERSION=$(gh release list \
    --repo kubernetes/cloud-provider-openstack \
    --json tagName \
    --jq '
        [ .[]
          | select(.tagName | startswith("openstack-cloud-controller-manager-"))
        ]
        | first
        | .tagName
        | sub("openstack-cloud-controller-manager-"; "")
    ')

sed -i "/name: openstack-cloud-controller-manager/,/version:/ s/version: .*/version: $CHART_VERSION/" .charts.yml
go run github.com/vexxhost/chart-vendor@latest --charts-root magnum_cluster_api/charts
