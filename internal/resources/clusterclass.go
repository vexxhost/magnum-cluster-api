// Copyright (c) VEXXHOST, Inc.
// SPDX-License-Identifier: Apache-2.0

package resources

import (
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/utils/ptr"
	capov1beta1 "sigs.k8s.io/cluster-api-provider-openstack/api/v1beta1"
	clusterv1beta1 "sigs.k8s.io/cluster-api/api/v1beta1"
	bootstrapkubeadmv1beta1 "sigs.k8s.io/cluster-api/bootstrap/kubeadm/api/v1beta1"
	controlplanekubeadmv1beta1 "sigs.k8s.io/cluster-api/controlplane/kubeadm/api/v1beta1"

	"github.com/vexxhost/magnum-cluster-api/internal/utils"
)

var (
	ClusterClass = &clusterv1beta1.ClusterClass{
		TypeMeta: metav1.TypeMeta{
			APIVersion: clusterv1beta1.GroupVersion.String(),
			Kind:       "ClusterClass",
		},
		ObjectMeta: ObjectMeta(),
		Spec: clusterv1beta1.ClusterClassSpec{
			Infrastructure: clusterv1beta1.LocalObjectTemplate{
				Ref: &corev1.ObjectReference{
					APIVersion: utils.GroupVersionKind(&capov1beta1.OpenStackClusterTemplate{}).GroupVersion().String(),
					Kind:       utils.GroupVersionKind(&capov1beta1.OpenStackClusterTemplate{}).Kind,
					Name:       ObjectMeta().Name,
					Namespace:  ObjectMeta().Namespace,
				},
			},
			ControlPlane: clusterv1beta1.ControlPlaneClass{
				LocalObjectTemplate: clusterv1beta1.LocalObjectTemplate{
					Ref: &corev1.ObjectReference{
						APIVersion: utils.GroupVersionKind(&controlplanekubeadmv1beta1.KubeadmControlPlaneTemplate{}).GroupVersion().String(),
						Kind:       utils.GroupVersionKind(&controlplanekubeadmv1beta1.KubeadmControlPlaneTemplate{}).Kind,
						Name:       ObjectMeta().Name,
						Namespace:  ObjectMeta().Namespace,
					},
				},
				MachineInfrastructure: &clusterv1beta1.LocalObjectTemplate{
					Ref: &corev1.ObjectReference{
						APIVersion: utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).GroupVersion().String(),
						Kind:       utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).Kind,
						Name:       ObjectMeta().Name,
						Namespace:  ObjectMeta().Namespace,
					},
				},
				MachineHealthCheck: &clusterv1beta1.MachineHealthCheckClass{
					UnhealthyConditions: []clusterv1beta1.UnhealthyCondition{
						{
							Type:    "Ready",
							Timeout: metav1.Duration{Duration: 5 * time.Minute},
							Status:  "False",
						},
						{
							Type:    "Ready",
							Timeout: metav1.Duration{Duration: 5 * time.Minute},
							Status:  "Unknown",
						},
					},
					MaxUnhealthy: ptr.To(intstr.FromString("80%")),
				},
				NodeVolumeDetachTimeout: &metav1.Duration{Duration: 5 * time.Minute},
			},
			Workers: clusterv1beta1.WorkersClass{
				MachineDeployments: []clusterv1beta1.MachineDeploymentClass{
					{
						Class: "default-worker",
						Template: clusterv1beta1.MachineDeploymentClassTemplate{
							Bootstrap: clusterv1beta1.LocalObjectTemplate{
								Ref: &corev1.ObjectReference{
									APIVersion: utils.GroupVersionKind(&bootstrapkubeadmv1beta1.KubeadmConfigTemplate{}).GroupVersion().String(),
									Kind:       utils.GroupVersionKind(&bootstrapkubeadmv1beta1.KubeadmConfigTemplate{}).Kind,
									Name:       ObjectMeta().Name,
									Namespace:  ObjectMeta().Namespace,
								},
							},
							Infrastructure: clusterv1beta1.LocalObjectTemplate{
								Ref: &corev1.ObjectReference{
									APIVersion: utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).GroupVersion().String(),
									Kind:       utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).Kind,
									Name:       ObjectMeta().Name,
									Namespace:  ObjectMeta().Namespace,
								},
							},
						},
						MachineHealthCheck: &clusterv1beta1.MachineHealthCheckClass{
							UnhealthyConditions: []clusterv1beta1.UnhealthyCondition{
								{
									Type:    "Ready",
									Timeout: metav1.Duration{Duration: 5 * time.Minute},
									Status:  "False",
								},
								{
									Type:    "Ready",
									Timeout: metav1.Duration{Duration: 5 * time.Minute},
									Status:  "Unknown",
								},
							},
							MaxUnhealthy: ptr.To(intstr.FromString("80%")),
						},
						NodeVolumeDetachTimeout: &metav1.Duration{Duration: 5 * time.Minute},
					},
				},
			},
			Variables: []clusterv1beta1.ClusterClassVariable{},
			Patches:   []clusterv1beta1.ClusterClassPatch{},
		},
	}
)
