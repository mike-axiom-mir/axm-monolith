# START HERE — AXM Monolith

**Nickname: The Assembly**

This repository is an integration/test surface, not a new home for the individual AXM projects.

## Mission

Create a reproducible on-demand snapshot of the current **public AXM repository stack** so a human or machine can inspect and test the whole accumulated system from one place.

The Assembly must preserve source identity.

A monolith is allowed to contain many modules. It is not allowed to pretend that separately evolved modules were always one codebase.

## Current hold

**Do not create the first monolith yet.**

The current growth batch still needs to be merged/reconciled. This repository should remain a prepared assembler until an explicit instruction is given to capture the stack.

Until that instruction:

- do not run `build`;
- do not commit generated stack lock files;
- do not vendor current repository mains into this repository;
- do not infer that the current public heads are the desired first test snapshot.

Read-only inspection of this repository is fine. Changes to the assembler itself should preserve the hold.

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

The assembler deliberately calls the public user-repository endpoint and still re-checks each repository's `private`/`visibility` fields before it becomes eligible.

## Explicit exclusion

`mike-axiom-mir/axm-collaboration-platform` is excluded by policy.

Reason: its protocols form a protected boundary. It may later cooperate through an explicit interface, but direct source absorption would defeat that separation.

`mike-axiom-mir/axm-monolith` is also always excluded to prevent recursive self-assembly.

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

If a repository moves after planning, the build still uses the pinned SHA. That is the point of the lock.

## What not to do

Do not:

- use `/user/repos` or another authenticated-private discovery endpoint;
- add private repos because the machine can see them;
- flatten files from multiple repos into one namespace;
- edit source modules inside a generated build and then quietly treat those edits as canonical upstream changes;
- interpret assembly success as compatibility success;
- connect the collaboration platform directly to bypass its own protocol boundary;
- run the first real build before the growth merges are ready.

## Commands and side effects

`discover` — network read only; prints repository selection to stdout.

`plan` — network read only; additionally resolves exact default-branch SHAs and prints the plan to stdout.

`build` — writes only to the explicitly supplied output directory. It requires `--confirm-build` and refuses a non-empty output directory. It does not modify source repos.

## First real experiment, later

When the hold is explicitly released:

1. run `discover` and inspect exclusions/rejections;
2. run `plan` and preserve the output for review;
3. only then run `build --confirm-build`;
4. inventory what actually assembled;
5. test modules individually first;
6. map duplicate concepts, incompatible interfaces, and missing connectors;
7. test combinations without upgrading evidence beyond what was actually observed;
8. feed repairs back to the owning source repos rather than silently forking them in the generated monolith.

## Constitutional boundary

Inside AXM, the four roots remain the constitutional merge gate:

- Truth
- Agency / non-domination
- Continuity
- Wisdom before speed

The Assembly does not gain authority over source projects merely because it can place their files next to each other.
