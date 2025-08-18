package main

import (
	"fmt"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/yaml"

	"github.com/vexxhost/magnum-cluster-api/internal/clusterclass"
	_ "github.com/vexxhost/magnum-cluster-api/internal/features"
)

func main() {
	cc := clusterclass.GetDefaultClusterClass(metav1.ObjectMeta{
		Namespace: "default",
		Name:      "magnum",
	})

	out, err := yaml.Marshal(cc)
	if err != nil {
		fmt.Printf("error marshalling to YAML: %v\n", err)
		return
	}

	fmt.Printf("%s", out)
}
