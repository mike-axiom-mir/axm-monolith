# AXM source-declared callable capability contract v0.1

AXM already distinguishes capability discovery from capability execution. The connected Monolith experiment makes the next gap explicit: a source repository can describe what it does, while the execution fabric may still have no grounded way to invoke that capability.

This contract adds one deliberately narrow bridge between those states.

## Source declaration

A capability in `AXM_MODULE.json` may add a `callable` object using schema:

`axm.callable-capability/v0.1`

Two declaration kinds are admitted in v0.1:

- `module-export`: names a repository-relative source file and one exported symbol;
- `command`: names a command surface, optionally anchored to a repository-relative path.

Every descriptor must say `authority: "none"`.

Example:

```json
{
  "id": "asset.workshop-lod-select",
  "provides": ["asset.lod-selection"],
  "accepts": ["view.camera-distance"],
  "callable": {
    "schema": "axm.callable-capability/v0.1",
    "kind": "module-export",
    "runtime": "javascript-esm",
    "path": "src/assets/workshop-lod-installer.mjs",
    "export": "selectWorkshopLodForView",
    "input_contract": "axm.global-state-rts.workshop-lod-view/v0.1",
    "output_contract": "axm.global-state-rts.workshop-lod-selection/v0.1",
    "authority": "none",
    "network": "none"
  }
}
```

## What Monolith may infer

`tools/callable_registry.py` may validate and preserve a source declaration as:

`declared_callable_not_exercised`

That means only:

1. the source repository explicitly identified a callable surface;
2. the descriptor shape is accepted;
3. repository-relative paths remain inside the source module;
4. a declared module-export file exists in the captured snapshot.

It does **not** mean the callable was imported, invoked, composed, safe, fast, correct, authorized, or accepted by another module.

Invalid declarations are retained as:

`blocked_invalid_callable_declaration`

They do not silently fall back to inferred execution.

## Execution promotion

A future execution fabric may consume this registry, but it must still validate the exact runtime and binding before setting `source_capability_execution: true`.

A suggested evidence ladder is:

```text
declared_callable_not_exercised
-> binding_validated_not_exercised
-> exercised_with_receipt
-> exact_composition_exercised
```

No rung grants merge/CANON authority. No successful invocation upgrades unrelated capabilities.

## Why this exists

The connected Monolith can currently address far more capabilities than it can actually call. Hard-coding every repository into the Monolith would turn the assembler into a permanent ownership bottleneck.

The source-declared contract instead lets each module publish its own bounded call surface while Monolith remains an inspector/router/evidence consumer. This keeps source identity, offline/local operation, provenance, and fail-closed execution boundaries intact.
