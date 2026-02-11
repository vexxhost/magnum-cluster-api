# Isolated Clusters

Isolated clusters are workload clusters that do not have a floating IP attached
to the Kubernetes API server. This is useful in environments where
exposing the API server to the internet is not possible or desirable.

In order to allow the management cluster to communicate with the workload
cluster's API server, the `magnum-cluster-api-proxy` service is used to proxy
traffic from the management cluster to the workload cluster through the
underlying Neutron network.

## Architecture

The proxy service can be deployed in several ways:

- Kubernetes-based (DaemonSet)
- Non-Kubernetes-based (systemd service)

Regardless of deployment method, the proxy must run on nodes that have network
connectivity to the workload cluster networks.

Each proxy instance performs the following tasks every 10 seconds:

1. **Discovers proxied clusters** by listing all `OpenStackCluster` resources
   and checking which ones have `disableAPIServerFloatingIP` set to `true` (or
   if the `PROXY_ALWAYS` environment variable is set).

2. **Checks network reachability** by looking for a Linux network namespace on
   the local node that matches the cluster's Neutron network ID. If no matching
   namespace exists, the proxy pod skips that cluster.

3. **Starts and manages HAProxy** with a configuration that uses TLS SNI-based
   routing to forward traffic to the correct workload cluster API server.

4. **Creates a Kubernetes Service** (without a selector) in the `magnum-system`
   namespace for each proxied cluster, named after the cluster. The service
   listens on port `6443`.

5. **Creates an EndpointSlice** for each proxied cluster, pointing to the
   proxy's reachable IP address (e.g. pod IP or node IP) and the HAProxy port. This links the Service to the local HAProxy instance.

6. **Rewrites the kubeconfig** secret for each proxied cluster to use the
   internal Kubernetes DNS name
   (e.g. `https://<cluster-name>.magnum-system:6443`) as the server URL.

7. **Cleans up** stale EndpointSlices that have not been updated within 30
   seconds, as well as Services for clusters that no longer exist.

### Traffic Flow

When a component in the management cluster (e.g. `magnum-conductor`) needs to
communicate with a workload cluster's API server, the following happens:

```
Client (e.g. magnum-conductor)
  │
  │  connects to https://<cluster-name>.magnum-system:6443
  │
  ▼
CoreDNS resolves <cluster-name>.magnum-system → Service ClusterIP
  │
  ▼
kube-proxy iptables DNAT → proxy IP:HAProxy port
  │
  ▼
HAProxy reads TLS SNI (<cluster-name>.magnum-system) from ClientHello
  │  SNI is in the TLS payload, not affected by DNAT
  │
  ▼
HAProxy selects backend "<cluster-name>.magnum-system"
  │  forwards inside the correct Linux network namespace
  │
  ▼
Workload cluster kube-apiserver (<api-server-ip>:6443)
```

### SNI-Based Routing

HAProxy operates at the TCP layer but inspects the TLS `ClientHello` message to
extract the Server Name Indication (SNI) hostname. This is the key mechanism
that allows a single HAProxy instance to route traffic to multiple workload
clusters:

- The SNI value is part of the TLS handshake **payload**, not the IP headers
- DNAT (performed by iptables/kube-proxy) only modifies IP/port headers and
  does **not** alter the TLS payload
- Therefore, HAProxy can always determine the target cluster regardless of any
  IP address translation

Each workload cluster gets a backend that forwards traffic to the cluster's
internal API server IP inside the appropriate network namespace:

```
backend <cluster-name>.magnum-system
  server apiserver <api-server-ip>:6443 namespace <network-namespace> check
```

### Multi-Instance Proxy

The proxy is designed to run on multiple nodes simultaneously. Each instance
independently:

- Discovers which clusters it can reach based on local network namespaces
- Creates its own EndpointSlice (named `<cluster>-<hostname>`)
- Manages its own HAProxy instance

Different instances may reach different sets of clusters depending on which
network namespaces are available on their respective nodes. When multiple
instances can reach the same cluster, the Service will have multiple
EndpointSlice entries, and kube-proxy will load-balance across them.

The Service is created **without a selector**, meaning Kubernetes does not
automatically manage its endpoints. Only instances that are actively running
HAProxy and have a healthy backend will register themselves as endpoints. If a
backend becomes unhealthy, the instance deletes the corresponding EndpointSlice.
