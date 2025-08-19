// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package clusterclass

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
	capov1beta1 "sigs.k8s.io/cluster-api-provider-openstack/api/v1beta1"
)

var (
	DefaultOpenStackClusterTemplate = capov1beta1.OpenStackClusterTemplate{
		TypeMeta: metav1.TypeMeta{
			APIVersion: capov1beta1.SchemeGroupVersion.String(),
			Kind:       "OpenStackClusterTemplate",
		},
		Spec: capov1beta1.OpenStackClusterTemplateSpec{
			Template: capov1beta1.OpenStackClusterTemplateResource{
				Spec: capov1beta1.OpenStackClusterSpec{
					APIServerLoadBalancer: &capov1beta1.APIServerLoadBalancer{},
					IdentityRef: capov1beta1.OpenStackIdentityReference{
						Name:      "PLACEHOLDER",
						CloudName: "default",
					},
					ManagedSecurityGroups: &capov1beta1.ManagedSecurityGroups{
						AllowAllInClusterTraffic: true,
						AllNodesSecurityGroupRules: []capov1beta1.SecurityGroupRuleSpec{
							{
								Name:           "Node Port (UDP, anywhere)",
								Direction:      "ingress",
								EtherType:      ptr.To("IPv4"),
								PortRangeMin:   ptr.To(30000),
								PortRangeMax:   ptr.To(32767),
								Protocol:       ptr.To("udp"),
								RemoteIPPrefix: ptr.To("0.0.0.0/0"),
							},
							{
								Name:           "Node Port (TCP, anywhere)",
								Direction:      "ingress",
								EtherType:      ptr.To("IPv4"),
								PortRangeMin:   ptr.To(30000),
								PortRangeMax:   ptr.To(32767),
								Protocol:       ptr.To("tcp"),
								RemoteIPPrefix: ptr.To("0.0.0.0/0"),
							},
						},
					},
				},
			},
		},
	}
)
