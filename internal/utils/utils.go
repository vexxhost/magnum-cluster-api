// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package utils

import (
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	capov1beta1 "sigs.k8s.io/cluster-api-provider-openstack/api/v1beta1"
	clusterv1beta1 "sigs.k8s.io/cluster-api/api/v1beta1"
	bootstrapkubeadmv1beta1 "sigs.k8s.io/cluster-api/bootstrap/kubeadm/api/v1beta1"
	controlplanekubeadmv1beta1 "sigs.k8s.io/cluster-api/controlplane/kubeadm/api/v1beta1"
)

func GroupVersionKind(obj runtime.Object) schema.GroupVersionKind {
	scheme := runtime.NewScheme()

	capov1beta1.AddToScheme(scheme)
	clusterv1beta1.AddToScheme(scheme)
	bootstrapkubeadmv1beta1.AddToScheme(scheme)
	controlplanekubeadmv1beta1.AddToScheme(scheme)

	gvks, _, _ := scheme.ObjectKinds(obj)
	return gvks[0]
}
