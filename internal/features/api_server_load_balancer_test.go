// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package features

import (
	"testing"

	"github.com/stretchr/testify/require"
	"k8s.io/apimachinery/pkg/runtime"
	capov1beta1 "sigs.k8s.io/cluster-api-provider-openstack/api/v1beta1"
)

func TestApiServerLoadBalancerFeature(t *testing.T) {
	desired := ValidatePatch(t, &ApiServerLoadBalancerFeature{}, map[string]interface{}{
		"apiServerLoadBalancer": map[string]interface{}{
			"enabled":  true,
			"provider": "amphora",
		},
	})

	var osc capov1beta1.OpenStackCluster
	require.NoError(t, runtime.DefaultUnstructuredConverter.FromUnstructured(
		desired.InfrastructureCluster.Object, &osc,
	))

	require.NotNil(t, osc.Spec.APIServerLoadBalancer)
	require.True(t, *osc.Spec.APIServerLoadBalancer.Enabled)
	require.Equal(t, "amphora", *osc.Spec.APIServerLoadBalancer.Provider)
}
