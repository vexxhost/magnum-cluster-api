set -euo pipefail

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
go run github.com/vexxhost/chart-vendor@latest
