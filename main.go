package main

import (
	"fmt"

	"sigs.k8s.io/yaml"

	"github.com/vexxhost/magnum-cluster-api/internal/clusterclass"
	_ "github.com/vexxhost/magnum-cluster-api/internal/features"
)

func main() {
	cc := clusterclass.GetDefaultClusterClass()

	out, err := yaml.Marshal(cc)
	if err != nil {
		fmt.Printf("error marshalling to YAML: %v\n", err)
		return
	}

	fmt.Printf("%s", out)
}
