# How a Magnum label flows through the driver

Magnum cluster template / cluster labels are how operators configure a cluster.
In `magnum-cluster-api` a single label may pass through up to **three** layers
before it changes a piece of generated YAML.  This document describes those
layers so contributors know where to add new labels and where to look when
debugging "I set this label, why didn't it take effect?".

## The three layers

```
┌────────────────────────────────────────────────────────────┐
│ Layer 1 — Python: label lookup (utils.py, resources.py)    │
│   Reads `cluster.labels[<name>]` (str → typed value).      │
│   Applies defaults, normalisation, validation.             │
│   May derive *additional* booleans from a single label     │
│   (e.g. `master_lb_floating_ip_enabled` →                  │
│   `disableAPIServerFloatingIP` +                           │
│   `disableAPIServerFloatingIPManaged`).                    │
└──────────────────────┬─────────────────────────────────────┘
                       │ injected as ClusterTopology variables
                       ▼
┌────────────────────────────────────────────────────────────┐
│ Layer 2 — Rust: feature module (src/features/<name>.rs)    │
│   Defines a `FeatureValues` struct with `serde(rename =    │
│   "<camelCase>")` for each ClusterClass variable it        │
│   consumes.  Emits `ClusterClassPatches` gated on those    │
│   variables.                                               │
└──────────────────────┬─────────────────────────────────────┘
                       │ JSON Patches applied at template-render time
                       ▼
┌────────────────────────────────────────────────────────────┐
│ Layer 3 — CAPI / CAPO: ClusterClass topology resolves the  │
│   patches against the underlying templates                 │
│   (KubeadmControlPlaneTemplate, OpenStackClusterTemplate,  │
│   OpenStackMachineTemplate, KubeadmConfigTemplate).        │
│   The result is the final spec for each managed resource.  │
└────────────────────────────────────────────────────────────┘
```

## Adding a new label — checklist

1. **Decide the data type.**  Magnum labels are strings on the wire.  Decide
   the parsed type your feature wants (`bool`, `String`, list, …).
2. **Layer 1.**  Add a getter / parser in `magnum_cluster_api/utils.py`
   (or extend `magnum_cluster_api/resources.py` if it's a per-cluster
   variable).  Add a default that matches existing semantics so untouched
   clusters do not regress.
3. **Layer 2.**  Add a field to the relevant `FeatureValues` struct in
   `src/features/<feature>.rs` with `#[serde(rename = "<camelCase>")]`.
   Emit any `ClusterClassPatches` you need.  Gate optional behaviour with
   `enabledIf: "{{ if .yourCamelCaseVar }}true{{end}}"`.
4. **Layer 3.**  Verify the rendered YAML in unit tests
   (`cargo test --lib <feature>`) — the `TestClusterResources` helper
   applies the patches against the template defaults so you can assert
   the final shape.
5. **Docs.**  Add an entry under the appropriate section of
   `docs/user/labels.md`.  Include: default value, supported values, and
   the **operational consequence** (not just "what flag it sets").

## Common pitfalls

* **Single label drives multiple variables.**  Some labels split into
  several variables for downstream gating — for example,
  `master_lb_floating_ip_enabled` populates *both*
  `disableAPIServerFloatingIP` (the actual boolean) *and*
  `disableAPIServerFloatingIPManaged` (a presence flag that activates the
  patch).  See `src/immutable_fields.rs` and
  `src/features/disable_api_server_floating_ip.rs` for the canonical
  example.

* **Variable name vs. label name.**  ClusterClass variables are camelCase
  (`disableAPIServerFloatingIP`); Magnum labels are snake_case
  (`master_lb_floating_ip_enabled`).  These are not always direct
  translations of each other — always check `resources.py` for the actual
  mapping.

* **Adding a label with no warning on typo.**  Magnum silently ignores
  labels it does not understand; if a label has no effect, double-check
  the spelling against `magnum_cluster_api/utils.py`.

* **Rust variable count test.**  If you add a new ClusterClass variable,
  `src/resources.rs` has `test_convert_values_to_cluster_topology_variables`
  which asserts the total number of variables; bump the expected count.

## Where each existing label lives

For the user-facing list with defaults and operational consequences,
see [`docs/user/labels.md`](../user/labels.md).

For the ClusterClass variable shape (Layer 2 → Layer 3), grep for the
`#[serde(rename = "...")]` attributes in `src/features/`.

For the Magnum label → variable mapping (Layer 1 → Layer 2), grep
`cluster.labels` in `magnum_cluster_api/utils.py` and
`magnum_cluster_api/resources.py`.
