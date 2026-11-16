# Authentication

## Application Credentials

When using the Cluster API driver for Magnum, OpenStack application credentials
are used for authentication between the cluster and the OpenStack API. It is
important to understand the requirements for creating these application
credentials to avoid common issues.

### Unrestricted Application Credentials

**Important**: Application credentials used with Magnum clusters **must** be
created with the `--unrestricted` flag to function properly.

When creating application credentials without the `--unrestricted` option, you
may encounter errors such as:

```
Failed to create trustee or trust for Cluster
```

This occurs because non-unrestricted application credentials have limited
permissions that prevent them from creating the necessary trust relationships
that Magnum requires for cluster management operations.

### Creating Application Credentials

To create an application credential that will work with Magnum clusters, use
the following command:

```bash
openstack application credential create --unrestricted <credential-name>
```

For example:

```bash
openstack application credential create --unrestricted magnum-cluster-api
```

This will output the application credential ID and secret that you can then
use to configure authentication for your Magnum clusters.

### Why Unrestricted is Required

The `--unrestricted` flag allows the application credential to:

- Create and manage trust relationships with Keystone
- Create trustee users for cluster operations
- Perform all necessary OpenStack API operations required for cluster
  lifecycle management

Without these permissions, the Cluster API driver for Magnum cannot properly
manage the cluster's integration with OpenStack services.

### Security Considerations

While using unrestricted application credentials provides the necessary
permissions for Magnum operations, consider the following security best
practices:

- Limit the scope of the application credential to the specific project
  where clusters will be created
- Regularly rotate application credentials
- Monitor the usage of application credentials
- Remove unused application credentials promptly

### Troubleshooting

If you encounter trust or trustee creation errors with existing clusters that
were created with restricted application credentials, you will need to:

1. Create a new unrestricted application credential
2. Update the cluster's cloud configuration to use the new credentials

For detailed steps on updating cluster credentials, see the
[Troubleshooting](troubleshooting.md) section.