// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package features

import (
	clusterv1 "sigs.k8s.io/cluster-api/api/v1beta1"
)

type Feature interface {
	Variables() []clusterv1.ClusterClassVariable
	Patches() []clusterv1.ClusterClassPatch
}
