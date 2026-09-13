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
  "id": "asset.workshop-lod-selection",
  "provides": ["asset.lod-selection"],
  "accepts": ["view.camera-distance"],
  "callable": {
    "schema": "axm.callable-capability/v0.1",
    "kind": "module-export",
    "runtime": "javascript-esm",
    "path": "src/assets/workshop-lod-policy.mjs",
    "export": "selectWorkshopRuntimeLod",
    "input_contract": "axm.global-state-rts.workshop-camera-distance/v0.1",
    "output_contract": "axm.global-state-rts.workshop-runtime-lod-policy/v0.1",
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

## Explicit execution rung

`tools/invoke_declared_callable.py` is deliberately separate from assembly and registry discovery. It never runs automatically.

v0.1 supports only:

- `kind: module-export`;
- `runtime: javascript-esm`;
- an explicit `--allow-javascript-esm` opt-in;
- one JSON request envelope containing positional `args`.

The helper does not use a shell. `command` declarations and unsupported runtimes remain blocked.

A successful invocation writes an `axm.monolith.callable-invocation-receipt/v0.1` receipt bound to:

- exact module/capability address;
- native manifest SHA-256;
- exact callable source-file SHA-256;
- canonical request SHA-256;
- canonical response SHA-256;
- runtime/export identity.

The resulting status may be `exercised_with_receipt` for that exact invocation. The capability registry itself remains a declaration registry rather than silently rewriting maturity from one run.

Source execution still occurs with the host process permissions of the environment in which the user explicitly invoked it. v0.1 is not a process/network sandbox.

## Execution promotion

The evidence ladder is:

```text
declared_callable_not_exercised
-> exercised_with_receipt
-> exact_composition_exercised
```

Additional binding-validation rungs may be added where a runtime needs them. No rung grants merge/CANON authority. No successful invocation upgrades unrelated capabilities.

## Why this exists

The connected Monolith can currently address far more capabilities than it can actually call. Hard-coding every repository into the Monolith would turn the assembler into a permanent ownership bottleneck.

The source-declared contract instead lets each module publish its own bounded call surface while Monolith remains an inspector/router/evidence consumer. This keeps source identity, offline/local operation, provenance, explicit execution consent, and fail-closed boundaries intact.
