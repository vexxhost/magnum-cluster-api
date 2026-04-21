# Cluster API driver for Magnum

## Checklist for work

When completing any work, make sure that the following is completed:

- All potential regressions are accounted for
- "pre-commit" has been ran on the codebase.

## Regressions

### Immutable-field preservation

- `src/immutable_fields.rs` has a resolver that reads the existing
  `OpenStackCluster` spec and overrides topology variables to preserve fields
  that CAPO's admission webhook considers immutable. Adding a new
  `FieldMapping` is only half the fix.
- The Python `Cluster.get_object` builder in `magnum_cluster_api/resources.py`
  **must** source every resolver-owned key from the `variables` dict returned
  by `self.rust_driver.resolve_immutable_fields(...)`, the way
  `apiServerLoadBalancer` does at `resources.py:1048`. Recomputing the value
  from labels or `utils.*` helpers silently discards the resolver output.
- This applies to companion/gating flags too (e.g.
  `disableAPIServerFloatingIPManaged`), not just the primary field.
- The `mock_rust_driver` fixture in `magnum_cluster_api/tests/unit/conftest.py`
  stubs `rust_driver.resolve_immutable_fields` as an identity function, so
  any Python unit test that uses it will not fail when builder wiring is
  missing. Cover the wiring with a Rust-side test, or a Python test that
  does not rely on that fixture.
