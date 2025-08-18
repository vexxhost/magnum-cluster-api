package clusterclass

import metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

var (
	DefaultClusterClass = GetDefaultClusterClass(metav1.ObjectMeta{})
)
