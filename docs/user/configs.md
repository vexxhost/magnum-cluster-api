# Configuration Options

The Cluster API driver for Magnum extends magnum configuration by adding these
driver-specific configuration options.

## auto_scaling
Options under this group are used for auto scaling.

`image_repository`

:   Image repository for the cluster auto-scaler.
    **Type**: `string`
    **Default value**: `registry.k8s.io/autoscaling`

`v1_22_image`

:   Image for the cluster auto-scaler for Kubernetes v1.22.
    **Type**: `string`
    **Default value**: `$image_repository/cluster-autoscaler:v1.22.3`

`v1_23_image`

:   Image for the cluster auto-scaler for Kubernetes v1.23.
    **Type**: `string`
    **Default value**: `$image_repository/cluster-autoscaler:v1.23.1`

`v1_24_image`

:   Image for the cluster auto-scaler for Kubernetes v1.24.
    **Type**: `string`
    **Default value**: `$image_repository/cluster-autoscaler:v1.24.2`

`v1_25_image`

:   Image for the cluster auto-scaler for Kubernetes v1.25.
    **Type**: `string`
    **Default value**: `$image_repository/cluster-autoscaler:v1.25.2`

`v1_26_image`

:   Image for the cluster auto-scaler for Kubernetes v1.26.
    **Type**: `string`
    **Default value**: `$image_repository/cluster-autoscaler:v1.26.3`

`v1_27_image`

:   Image for the cluster auto-scaler for Kubernetes v1.27.
    **Type**: `string`
    **Default value**: `$image_repository/cluster-autoscaler:v1.27.2`

## manila_client
Options under this group are used for configuring Manila client.

`region_name`

:   Region in Identity service catalog to use for communication with the OpenStack service.
    **Type**: `string`

`endpoint_type`

:   Type of endpoint in Identity service catalog to use for communication with the OpenStack service.
    **Type**: `string`
    **Default value**: `publicURL`

`api_version`

:   Version of Manila API to use in manilaclient.
    **Type**: `string`
    **Default value**: `3`

`ca_file`

:   Optional CA cert file to use in SSL connections.
    **Type**: `string`

`cert_file`

:   Optional PEM-formatted certificate chain file.
    **Type**: `string`

`key_file`

:   Optional PEM-formatted file that contains the private key.
    **Type**: `string`

`insecure`

:   If set, then the server's certificate will not be verified.
    **Type**: `boolean`
    **Default value**: `False`

## capi_client
Options under this group are used for configuring Openstack authentication for CAPO.

`endpoint_type`

:   Type of endpoint in Identity service catalog to use for communication with the OpenStack service.
    **Type**: `string`
    **Default value**: `publicURL`

`ca_file`

:   Optional CA cert file to use in SSL connections.
    **Type**: `string`

`insecure`

:   If set, then the server's certificate will not be verified.
    **Type**: `boolean`
    **Default value**: `False`

## cinder
Options under this group are used for configuring OpenStack Cinder behavior.

`cross_az_attach`

:   When set to False, Cluster Availability Zone will be used to create a volume.
    For that Availability Zone names in Cinder and Nova should match.
    Otherwise, default `nova` Availability Zone will be used for volumes.
    **Type**: `boolean`
    **Default value**: `True`
