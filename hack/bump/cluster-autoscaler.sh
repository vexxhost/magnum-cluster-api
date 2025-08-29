set -euo pipefail

FILE=${1:-magnum_cluster_api/images.py}

# Build block with 4 spaces + trailing comma, sorted by minor asc.
# We join with literal "\n" so awk can turn it into real newlines.
BLOCK=$(
  gh api repos/kubernetes/autoscaler/tags --paginate \
  | jq -r '
      [ .[].name
        | select(test("^cluster-autoscaler-1\\.[0-9]+\\.[0-9]+$"))
        | capture("^cluster-autoscaler-(?<major>1)\\.(?<minor>\\d+)\\.(?<patch>\\d+)$")
        | .minor |= tonumber
        | .patch |= tonumber
      ]
      | map(select(.minor >= 22))
      | group_by(.minor)
      | map(max_by(.patch))
      | sort_by(.minor)
      | map({("1."+(.minor|tostring)): (.major+"."+(.minor|tostring)+"."+(.patch|tostring))})
      | add
      | to_entries
      | sort_by((.key|split(".")[1]|tonumber))
      | map("    \"" + .key + "\": \"" + .value + "\",")
      | join("\\n")
  '
)

# In-place replace contents of the dict block using awk.
awk -i inplace -v block="$BLOCK" '
function print_block() {
  tmp = block
  gsub(/\\n/, "\n", tmp)   # turn literal \n into real newlines
  printf "%s\n", tmp
}
# Detect the start of the dict
/^CLUSTER_AUTOSCALER_LATEST_BY_MINOR = \{$/ {
  print            # keep the opening line
  in_block = 1
  printed = 0
  next
}
# Detect the closing brace of the dict
in_block && /^\}/ {
  if (!printed) { print_block(); printed = 1 }
  in_block = 0
  print            # keep the closing brace
  next
}
# Skip old lines inside the block
in_block { next }

# Everything else prints as-is
{ print }
' "$FILE"

echo "Updated $FILE"
