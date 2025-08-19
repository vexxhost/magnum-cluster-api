// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package features

import (
	"k8s.io/utils/ptr"
	capov1beta1 "sigs.k8s.io/cluster-api-provider-openstack/api/v1beta1"
	clusterv1 "sigs.k8s.io/cluster-api/api/v1beta1"

	"github.com/vexxhost/magnum-cluster-api/internal/resources"
	"github.com/vexxhost/magnum-cluster-api/internal/utils"
)

type ApiServerLoadBalancerFeature struct{}

func init() {
	f := &ApiServerLoadBalancerFeature{}

	resources.ClusterClass.Spec.Variables = append(resources.ClusterClass.Spec.Variables, f.Variables()...)
	resources.ClusterClass.Spec.Patches = append(resources.ClusterClass.Spec.Patches, f.Patches()...)
}

func (f *ApiServerLoadBalancerFeature) Variables() []clusterv1.ClusterClassVariable {
	return []clusterv1.ClusterClassVariable{
		{
			Name:     "apiServerLoadBalancer",
			Required: true,
			Schema: clusterv1.VariableSchema{
				OpenAPIV3Schema: clusterv1.JSONSchemaProps{
					Type: "object",
					Properties: map[string]clusterv1.JSONSchemaProps{
						"enabled":  {Type: "boolean"},
						"provider": {Type: "string"},
					},
					Required: []string{"enabled", "provider"},
				},
			},
		},
	}
}

func (f *ApiServerLoadBalancerFeature) Patches() []clusterv1.ClusterClassPatch {
	gvk := utils.GroupVersionKind(&capov1beta1.OpenStackClusterTemplate{})

	return []clusterv1.ClusterClassPatch{
		{
			Name: "apiServerLoadBalancer",
			Definitions: []clusterv1.PatchDefinition{
				{
					Selector: clusterv1.PatchSelector{
						APIVersion: gvk.GroupVersion().String(),
						Kind:       gvk.Kind,
						MatchResources: clusterv1.PatchSelectorMatch{
							InfrastructureCluster: true,
						},
					},
					JSONPatches: []clusterv1.JSONPatch{
						{
							Op:   "add",
							Path: "/spec/template/spec/apiServerLoadBalancer",
							ValueFrom: &clusterv1.JSONPatchValue{
								Variable: ptr.To("apiServerLoadBalancer"),
							},
						},
					},
				},
			},
		},
	}
}
