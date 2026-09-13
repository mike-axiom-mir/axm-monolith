# START HERE — AXM Monolith

**Nickname: The Assembly**

This repository is an integration/test surface, not a new home for the individual AXM projects.

## Mission

Create a reproducible on-demand snapshot of the current **public AXM repository stack** so a human or machine can inspect and test the whole accumulated system from one place.

The Assembly must preserve source identity while making the combined capability surface understandable.

A monolith is allowed to contain many modules. It is not allowed to pretend that separately evolved modules were always one codebase or that co-location proves compatibility.

## Current state

The first-build hold has been released after a real snapshot and Blackline workflow experiment.
Builds remain explicit: `--confirm-build` is required, exact heads are pinned before capture,
generated modules remain outside this repository, and no source repository is modified.

## What is already prepared

Two layers now exist:

### 1. The assembler

`tools/assemble.py`

It can later discover the eligible public repo set, pin exact SHAs, materialize each source under its own namespace, and preserve provenance.

### 2. The capability inspector

`tools/inspect_stack.py`

After materialization it can deterministically inspect the captured modules and generate:

```text
OPEN_ME.html
STACK_REPORT.md
STACK_ANALYSIS.json
CAPABILITY_REGISTRY.json
CONNECTION_GRAPH.json
COMPOSITION_CANDIDATES.json
HUMAN_TEST_QUEUE.json
AUTOMATED_TEST_QUEUE.json
analysis/modules/<repo>.json
```

The dashboard is intentionally offline and dependency-free.

Capabilities are labelled by evidence source:

- native module declaration;
- structural file/package detection;
- bounded inference rule.

Candidate connections and routes are never silently labelled verified.

Read [`CAPABILITY_MODEL.md`](CAPABILITY_MODEL.md) for the detailed truth model.

## Selection invariant

The default discovery boundary is:

```text
owner == mike-axiom-mir
AND visibility == public
AND not explicitly excluded
AND not a fork (default)
AND not archived (default)
```

Private repository visibility must never be used as a convenience shortcut. A GitHub token may improve API limits, but it must not widen the source set.

The assembler deliberately calls the public user-repository endpoint and re-checks each repository's visibility before eligibility.

## Explicit exclusion

`mike-axiom-mir/axm-collaboration-platform` is excluded by policy.

Reason: its protocols form a protected boundary. It may later cooperate through an explicit interface, but direct source absorption would defeat that separation.

`mike-axiom-mir/axm-monolith` is always excluded to prevent recursive self-assembly.

Future exclusions belong in `config/assembly.json` with an explicit reason.

## Source integrity

Every future build must:

1. resolve repository heads first;
2. pin exact commit SHAs before materialization;
3. store those pins in the generated output;
4. materialize only the pinned SHAs;
5. write source identity/provenance per module;
6. keep modules namespaced;
7. never push changes back to source repositories as part of assembly.

If a repository moves after planning, the build still uses the pinned SHA.

## Capability integrity

The inspector may describe and compare captured modules, but it must not confuse evidence classes.

A README/name-based capability inference is weaker than structural detection. Structural detection is weaker than a tested composition. A declared native interface is still not automatically a successful runtime integration.

The first monolith should therefore expose:

```text
what exists
what is declared
what is structurally visible
what is inferred
what appears connectable
what has not been tested
```

rather than flattening those categories into one "works" status.

## What not to do

Do not:

- use `/user/repos` or another authenticated-private discovery endpoint;
- add private repos because the machine can see them;
- flatten files from multiple repos into one namespace;
- edit source modules inside a generated build and quietly treat those edits as upstream truth;
- interpret assembly success as compatibility success;
- interpret a graph edge as verified interoperability;
- auto-execute arbitrary discovered module tests during first assembly;
- connect the collaboration platform directly to bypass its own protocol boundary;
- run the first real build before the growth merges are ready.

## Commands and side effects

`discover` — network read only; prints repository selection.

`plan` — network read only; additionally resolves exact default-branch SHAs.

`build` — only after the config hold is released; writes to the supplied empty output directory, materializes the pinned public stack, then runs offline capability analysis.

`inspect` — offline; re-analyzes an already materialized build.

`tools/inspect_stack.py query` — offline; searches the generated capability surface.

`tools/inspect_stack.py route` — offline; finds a candidate graph route and labels it unverified.

## Repeatable build and connected-package experiment

1. run `discover` and inspect exclusions/rejections;
2. run `plan` and preserve the output for review;
3. run `build --confirm-build` only on the chosen moment;
4. open `OPEN_ME.html`;
5. inspect the full capability/evidence/connection surface;
6. use the human-test queue instead of manually hunting across every repo;
7. use `tools/finalize_connected_snapshot.py` to require selected execution evidence and package;
8. test selected candidate compositions;
9. feed real repairs back to the owning source repos rather than silently forking them in the monolith.

See [`CONNECTED_FINALIZATION.md`](CONNECTED_FINALIZATION.md).

## Constitutional boundary

Inside AXM, the four roots remain the constitutional merge gate:

- Truth
- Agency / non-domination
- Continuity
- Wisdom before speed

The Assembly does not gain authority over source projects merely because it can place their files and capability descriptions next to one another.
