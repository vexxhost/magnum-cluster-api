package clusterclass

import (
	"time"

	"github.com/vexxhost/magnum-cluster-api/internal/utils"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/utils/ptr"
	capov1beta1 "sigs.k8s.io/cluster-api-provider-openstack/api/v1beta1"
	clusterv1beta1 "sigs.k8s.io/cluster-api/api/v1beta1"
	bootstrapkubeadmv1beta1 "sigs.k8s.io/cluster-api/bootstrap/kubeadm/api/v1beta1"
	controlplanekubeadmv1beta1 "sigs.k8s.io/cluster-api/controlplane/kubeadm/api/v1beta1"
)

type ClusterClassBuilder struct {
	variables []clusterv1beta1.ClusterClassVariable
	patches   []clusterv1beta1.ClusterClassPatch
}

var defaultBuilder = NewBuilder()

func NewBuilder() *ClusterClassBuilder {
	return &ClusterClassBuilder{}
}

func DefaultBuilder() *ClusterClassBuilder {
	return defaultBuilder
}

func (b *ClusterClassBuilder) AddVariables(vars ...clusterv1beta1.ClusterClassVariable) {
	b.variables = append(b.variables, vars...)
}

func (b *ClusterClassBuilder) AddPatches(patches ...clusterv1beta1.ClusterClassPatch) {
	b.patches = append(b.patches, patches...)
}

func (b *ClusterClassBuilder) Build(metadata metav1.ObjectMeta) clusterv1beta1.ClusterClass {
	return clusterv1beta1.ClusterClass{
		TypeMeta: metav1.TypeMeta{
			APIVersion: clusterv1beta1.GroupVersion.String(),
			Kind:       "ClusterClass",
		},
		ObjectMeta: metadata,
		Spec: clusterv1beta1.ClusterClassSpec{
			Infrastructure: clusterv1beta1.LocalObjectTemplate{
				Ref: &corev1.ObjectReference{
					APIVersion: utils.GroupVersionKind(&capov1beta1.OpenStackClusterTemplate{}).GroupVersion().String(),
					Kind:       utils.GroupVersionKind(&capov1beta1.OpenStackClusterTemplate{}).Kind,
					Name:       metadata.Name,
					Namespace:  metadata.Namespace,
				},
			},
			ControlPlane: clusterv1beta1.ControlPlaneClass{
				LocalObjectTemplate: clusterv1beta1.LocalObjectTemplate{
					Ref: &corev1.ObjectReference{
						APIVersion: utils.GroupVersionKind(&controlplanekubeadmv1beta1.KubeadmControlPlaneTemplate{}).GroupVersion().String(),
						Kind:       utils.GroupVersionKind(&controlplanekubeadmv1beta1.KubeadmControlPlaneTemplate{}).Kind,
						Name:       metadata.Name,
						Namespace:  metadata.Namespace,
					},
				},
				MachineInfrastructure: &clusterv1beta1.LocalObjectTemplate{
					Ref: &corev1.ObjectReference{
						APIVersion: utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).GroupVersion().String(),
						Kind:       utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).Kind,
						Name:       metadata.Name,
						Namespace:  metadata.Namespace,
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
									Name:       metadata.Name,
									Namespace:  metadata.Namespace,
								},
							},
							Infrastructure: clusterv1beta1.LocalObjectTemplate{
								Ref: &corev1.ObjectReference{
									APIVersion: utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).GroupVersion().String(),
									Kind:       utils.GroupVersionKind(&capov1beta1.OpenStackMachineTemplate{}).Kind,
									Name:       metadata.Name,
									Namespace:  metadata.Namespace,
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
			Variables: b.variables,
			Patches:   b.patches,
		},
	}
}

func GetDefaultClusterClass(metadata metav1.ObjectMeta) clusterv1beta1.ClusterClass {
	return defaultBuilder.Build(metadata)
}
