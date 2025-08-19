package main

import (
	"fmt"

	"sigs.k8s.io/yaml"

	_ "github.com/vexxhost/magnum-cluster-api/internal/features"
	"github.com/vexxhost/magnum-cluster-api/internal/resources"
)

func main() {
	// cc := resources.GetClusterClass()
	cc := resources.ClusterClass

	out, err := yaml.Marshal(cc)
	if err != nil {
		fmt.Printf("error marshalling to YAML: %v\n", err)
		return
	}

	fmt.Printf("%s", out)
}
