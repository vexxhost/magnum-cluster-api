// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package resources

import (
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"github.com/vexxhost/magnum-cluster-api/version"
)

func ObjectMeta() metav1.ObjectMeta {
	return metav1.ObjectMeta{
		Name:      fmt.Sprintf("magnum-%s", version.Get().String()),
		Namespace: "magnum-system",
	}
}
