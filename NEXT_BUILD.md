# NEXT BUILD — Automated plumbing first

The obsolete first-snapshot hold is released. The next build is still deliberate and
point-in-time, but plumbing is no longer a manual repair step after assembly.

## Build sequence

1. Discover the eligible public owner repositories.
2. Resolve and review the exact-SHA plan.
3. Build with explicit confirmation.
4. Let the repository automatically generate aggregate and leaf catalogues, pipeline and
   callable registries, bounded runtimes, and the one-click local front door.
5. Execute selected native calls or named workflows with explicit inputs.
6. Package only after the required receipts pass.

```bash
python tools/assemble.py discover
python tools/assemble.py plan > next-plan.json
python tools/assemble.py build \
  --output ../axm-monolith-builds/<label> \
  --confirm-build
```

The build output is already plumbed. `START_AXM.cmd` or `START_AXM.sh` opens the single local
front door. `LEAF_CAPABILITY_REGISTRY.json` records the exact declared low-level identifiers;
`CALLABLE_CAPABILITY_REGISTRY.json` records only valid native callable contracts.

## Connected package

Use [`CONNECTED_FINALIZATION.md`](CONNECTED_FINALIZATION.md) for the one-command evidence and
packaging gate. A release may require exact native callable addresses, a named workflow, both,
or neither. When a route is required, missing or rejected receipts block packaging.

## Permanent truth boundary

- Co-location is not compatibility.
- A leaf ID is not a function.
- A callable declaration is not an execution.
- A candidate pipeline is not a connected route.
- A successful receipt applies only to the exact pinned source and request it identifies.

Failures and unbound capabilities remain visible. Repairs found through a snapshot still return
to their owning source repositories rather than silently turning the monolith into their new
canonical home.
