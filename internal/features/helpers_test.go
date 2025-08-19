// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package features

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
	apiextensionsv1 "k8s.io/apiextensions-apiserver/pkg/apis/apiextensions/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	capov1beta1 "sigs.k8s.io/cluster-api-provider-openstack/api/v1beta1"
	clusterv1 "sigs.k8s.io/cluster-api/api/v1beta1"
	"sigs.k8s.io/cluster-api/exp/topology/scope"
	"sigs.k8s.io/cluster-api/util/test/builder"

	"github.com/vexxhost/magnum-cluster-api/internal/clusterapi/controllers/topology/cluster/patches"
	fakeruntimeclient "github.com/vexxhost/magnum-cluster-api/internal/clusterapi/runtime/client/fake"
	"github.com/vexxhost/magnum-cluster-api/internal/resources"
)

func MustToUnstructured(t *testing.T, obj runtime.Object) *unstructured.Unstructured {
	m, err := runtime.DefaultUnstructuredConverter.ToUnstructured(obj)
	require.NoError(t, err, "failed to convert object to unstructured")

	return &unstructured.Unstructured{Object: m}
}

func ValidatePatch(t *testing.T, feature Feature, values map[string]interface{}) *scope.ClusterState {
	runtimeClient := fakeruntimeclient.NewRuntimeClientBuilder().Build()
	patchEngine := patches.NewEngine(runtimeClient)

	var clusterVariables []clusterv1.ClusterVariable
	for key, value := range values {
		raw, err := json.Marshal(value)
		require.NoError(t, err)

		clusterVariables = append(clusterVariables, clusterv1.ClusterVariable{
			Name:  key,
			Value: apiextensionsv1.JSON{Raw: raw},
		})
	}

	var clusterClassStatusVariables []clusterv1.ClusterClassStatusVariable
	for _, variable := range feature.Variables() {
		clusterClassStatusVariables = append(clusterClassStatusVariables, clusterv1.ClusterClassStatusVariable{
			Name: variable.Name,
			Definitions: []clusterv1.ClusterClassStatusVariableDefinition{
				{
					From: "inline",
				},
			},
		})
	}

	controlPlaneInfrastructureMachineTemplate := builder.InfrastructureMachineTemplate(metav1.NamespaceDefault, "controlplaneinframachinetemplate1").
		Build()

	controlPlaneTemplate := builder.ControlPlaneTemplate(metav1.NamespaceDefault, "controlPlaneTemplate1").
		WithInfrastructureMachineTemplate(controlPlaneInfrastructureMachineTemplate).
		Build()

	clusterClass := builder.ClusterClass(metav1.NamespaceDefault, "cluster-class").
		WithInfrastructureClusterTemplate(MustToUnstructured(t, &resources.OpenStackClusterTemplate)).
		WithPatches(feature.Patches()).
		WithVariables(feature.Variables()...).
		WithStatusVariables(clusterClassStatusVariables...).
		Build()

	cluster := &clusterv1.Cluster{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "cluster",
			Namespace: metav1.NamespaceDefault,
		},
		Spec: clusterv1.ClusterSpec{
			Topology: &clusterv1.Topology{
				Version:      "v1.21.2",
				Class:        clusterClass.Name,
				ControlPlane: clusterv1.ControlPlaneTopology{},
				Variables:    clusterVariables,
			},
		},
	}

	blueprint := &scope.ClusterBlueprint{
		Topology:                      cluster.Spec.Topology,
		ClusterClass:                  clusterClass,
		InfrastructureClusterTemplate: MustToUnstructured(t, &resources.OpenStackClusterTemplate),
		ControlPlane: &scope.ControlPlaneBlueprint{
			Template:                      controlPlaneTemplate,
			InfrastructureMachineTemplate: MustToUnstructured(t, &resources.OpenStackClusterTemplate),
		},
	}

	desired := &scope.ClusterState{
		Cluster:               cluster.DeepCopy(),
		InfrastructureCluster: MustToUnstructured(t, &capov1beta1.OpenStackCluster{}),
		ControlPlane: &scope.ControlPlaneState{
			Object: builder.ControlPlane(metav1.NamespaceDefault, "control-plane").
				WithVersion("v1.21.2").
				WithReplicas(3).
				WithInfrastructureMachineTemplate(MustToUnstructured(t, &resources.OpenStackClusterTemplate).DeepCopy()).
				Build(),
			InfrastructureMachineTemplate: MustToUnstructured(t, &resources.OpenStackClusterTemplate).DeepCopy(),
		},
	}

	err := patchEngine.Apply(context.Background(), blueprint, desired)
	require.NoError(t, err)

	return desired
}
