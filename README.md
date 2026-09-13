# AXM Monolith — The Assembly

**Nickname: The Assembly**

AXM Monolith is the on-demand integration and test surface for the public AXM stack.

Its job is **not** to become another development home and it is **not** allowed to silently fork or flatten the source repositories. Its job is to answer:

> **At this exact moment, what does the current public AXM stack become when we assemble it together without erasing the identity of its parts — and what can the assembled stack actually show us about its capabilities, connections, tests, and unknowns?**

## Current status

**The first real assembly has been exercised. New builds now install their discovery, callable, workflow, one-launch, evidence, and packaging plumbing automatically.**

`config/assembly.json` enables deliberate builds. A build still requires `--confirm-build`, remains public-only, pins exact source SHAs, preserves module namespaces, and does not modify source repositories.

Pipeline Fabric is a post-analysis capability. It consumes an existing `STACK_ANALYSIS.json` and exports a capability-level graph, bounded candidate pipelines, goal queries, and explicit gap/adapter leads for this exact snapshot. It does not execute pipelines or create authority.

The monolith can also export its **real checked-in assembly-control state** into AXM Machine Voice's strict notice snapshot format. The current enabled state emits normal silence; if a future explicit hold is recorded, the first rule reports only that hold without labelling it good, bad, important, anomalous, or failed.

A one-command local composition runner is also ready. When `axm-machine-voice` is physically present as a sibling (or explicitly selected path), it exports the real state, invokes the real Machine Voice zero-install channel, preserves a local communication journal, and writes explicit composition evidence. Repository CI tests that orchestration with a fake external process only; real cross-repository runtime evidence still requires the local/staged command. See [`MACHINE_VOICE_BRIDGE.md`](MACHINE_VOICE_BRIDGE.md).

## Source boundary

The default source set is intentionally simple:

- GitHub owner: `mike-axiom-mir`
- **PUBLIC repositories only**
- private repositories are rejected even if credentials can see them
- forks are excluded by default
- archived repositories are excluded by default
- explicit exclusions come from `config/assembly.json`
- this repository excludes itself to prevent recursion

The collaboration platform is explicitly excluded:

- `mike-axiom-mir/axm-collaboration-platform`

That exclusion is architectural. The collaboration platform may later be called across its own protocol boundary, but its internals must not be directly absorbed into the monolith.

## On-demand model

```text
discover   -> read-only list of eligible and rejected repositories
plan       -> read-only exact default-branch SHA plan
build      -> explicit materialization + automatic offline stack analysis
inspect    -> re-analyze an already materialized build without touching GitHub
pipeline   -> derive/query reusable capability-level pipeline possibilities from analysis
voice      -> export explicit monolith state into a strict Machine Voice snapshot
voice-test -> locally exercise that snapshot through a real Machine Voice checkout
```

Nothing materializes or executes source capabilities without an explicit command. Once a build
is explicitly confirmed, its non-source-executing plumbing pass runs automatically so the
snapshot cannot be packaged before registries, runtimes, launchers, and truth labels exist.

## What one confirmed build does

When a build is explicitly requested, The Assembly will:

1. discover only eligible public owner repositories;
2. apply explicit exclusions;
3. resolve exact current default-branch SHAs with bounded parallel API requests,
   transient retries, and a read-only Git fallback;
4. write `axm-stack.lock.json`;
5. materialize every pinned repo under `modules/<repo>`;
6. preserve per-module source/provenance;
7. inventory files, languages, entrypoints, tests, schemas, assets, and optional native AXM manifests;
8. build a capability registry;
9. map candidate cross-module interfaces without pretending they are verified;
10. derive bounded candidate composition chains;
11. produce a machine test-command queue and a separate human-test queue;
12. generate a dependency-free offline dashboard: **`OPEN_ME.html`**;
13. inventory exact declared leaf IDs separately from broad capability labels;
14. export candidate pipelines and a native callable registry;
15. install bounded invocation/ledger runtimes and one local front door.

The generated build will contain:

```text
axm-stack.lock.json
MONOLITH_MANIFEST.json
INVENTORY.md

OPEN_ME.html
STACK_REPORT.md
STACK_ANALYSIS.json
CAPABILITY_REGISTRY.json
CONNECTION_GRAPH.json
COMPOSITION_CANDIDATES.json
HUMAN_TEST_QUEUE.json
AUTOMATED_TEST_QUEUE.json
LEAF_CAPABILITY_REGISTRY.json
CALLABLE_CAPABILITY_REGISTRY.json
PLUMBING_RECEIPT.json
START_AXM.cmd
START_AXM.sh

analysis/modules/<repo>.json
modules/<repo>/...
```

Pipeline Fabric can then add portable post-analysis outputs:

```text
PIPELINE_FABRIC.json
PIPELINE_GRAPH.json
PIPELINE_CANDIDATES.json
PIPELINE_GAPS.json
```

So the first thing Mike needs to do after assembly is simply open `OPEN_ME.html`. Machines or later AXM systems can consume the machine-readable registry/graph/pipeline files directly.

For a release ZIP, use the evidence-gated finalizer in [`CONNECTED_FINALIZATION.md`](CONNECTED_FINALIZATION.md). It refuses to call a package connected merely because files share a folder or a graph has edges.

## Capability truth model

The inspector distinguishes three broad evidence sources:

```text
native manifest       -> explicitly declared by the source module
structural scan       -> deterministically visible in the captured files
inference rule        -> useful lead derived from repo/readme structure
```

None of those automatically proves cross-module runtime interoperability.

Candidate graph edges are labelled, for example:

```text
declared_contract_match_not_tested
structurally_possible_not_tested
inferred_candidate_not_tested
```

The Assembly never upgrades a candidate connection to `VERIFIED` merely because two repos were placed next to each other.

Pipeline Fabric carries that same rule through an entire route: a pipeline inherits the weakest evidence class of its edges and remains unexecuted until a separate composition experiment proves more.

See [`CAPABILITY_MODEL.md`](CAPABILITY_MODEL.md) and [`PIPELINE_FABRIC.md`](PIPELINE_FABRIC.md).

## Namespacing

The monolith must be whole without becoming identity soup.

```text
monolith/
  modules/
    axm-state-research/
    axm-universal-creation/
    axm-institution-fabric/
    axm-directional-state-fabric/
    ...
```

Same-named files never overwrite one another. Cross-module links are explicit graph relations or later adapters.

## Commands

Read-only discovery:

```bash
python tools/assemble.py discover
```

Read-only exact-head plan:

```bash
python tools/assemble.py plan
```

Deliberate build with automatic plumbing:

```bash
python tools/assemble.py build \
  --output ../axm-monolith-builds/<label> \
  --confirm-build
```

Re-run the offline analysis of an existing build:

```bash
python tools/assemble.py inspect --build ../axm-monolith-builds/<label>
```

Search capabilities after assembly:

```bash
python tools/inspect_stack.py query ../axm-monolith-builds/<label> game
python tools/inspect_stack.py query ../axm-monolith-builds/<label> state
```

Ask for a candidate path between modules:

```bash
python tools/inspect_stack.py route ../axm-monolith-builds/<label> axm-universal-creation axm-institution-fabric
```

Routes remain `candidate_route_not_verified` until exercised.

Export the deeper capability-level pipeline fabric:

```bash
python tools/pipeline_fabric.py export ../axm-monolith-builds/<label>
```

Ask what candidate pipelines could end in a particular output token:

```bash
python tools/pipeline_fabric.py goal ../axm-monolith-builds/<label> artifact.game-build
```

Ask where the current stack has missing providers, unused outputs, or possible adapter seams:

```bash
python tools/pipeline_fabric.py gaps ../axm-monolith-builds/<label>
```

Export the current checked-in assembly-control state as a strict Machine Voice notice snapshot:

```bash
python tools/export_machine_voice_state.py \
  --output .generated/machine-voice-composition/MACHINE_VOICE_NOTICE.json
```

Run the entire local Monolith → Machine Voice composition proof in one command when the sibling `../axm-machine-voice` checkout exists:

```bash
python tools/test_machine_voice_composition.py
```

For a Machine Voice checkout elsewhere:

```bash
python tools/test_machine_voice_composition.py \
  --machine-voice-root /path/to/axm-machine-voice
```

The default keeps `.generated/machine-voice-composition/MACHINE_VOICE_COMMUNICATION.jsonl`. A first fresh emission reports `verified_fresh_emission`; a later exact repeat may report `verified_duplicate_suppression`, which is also healthy continuity evidence. Use `--reset-journal` only when an explicit fresh-emission proof is wanted.

Other projects may consume exported files later, but they must preserve the evidence labels. A route is not permission, and possibility is not execution.

## Truth boundary

A successful assembly means the selected public repos were pinned, materialized, and inspected reproducibly.

It does **not** mean:

- the whole stack already works as one runtime;
- duplicated concepts are equivalent;
- inferred capabilities are proven;
- candidate graph edges are verified;
- candidate pipelines are executable or safe merely because a path exists;
- lexical adapter suggestions are semantically compatible;
- arbitrary discovered tests are safe to auto-run;
- an untested composition is safe;
- a Machine Voice snapshot export alone proves cross-repository runtime composition;
- a fake-process CI test proves the real Machine Voice sibling runtime works;
- one successful local Machine Voice bridge verifies unrelated AXM module connections;
- a module's claims become stronger merely because it is inside the monolith.

Those are exactly the questions The Assembly exists to make visible and testable.

## Start here

Future builders should read:

1. [`START_HERE.md`](START_HERE.md)
2. [`MONOLITH_BOUNDARY.md`](MONOLITH_BOUNDARY.md)
3. [`CAPABILITY_MODEL.md`](CAPABILITY_MODEL.md)
4. [`PIPELINE_FABRIC.md`](PIPELINE_FABRIC.md)
5. [`MACHINE_VOICE_BRIDGE.md`](MACHINE_VOICE_BRIDGE.md)
6. [`config/assembly.json`](config/assembly.json)
7. [`tools/assemble.py`](tools/assemble.py)
8. [`tools/inspect_stack.py`](tools/inspect_stack.py)
9. [`tools/pipeline_fabric.py`](tools/pipeline_fabric.py)
10. [`tools/export_machine_voice_state.py`](tools/export_machine_voice_state.py)
11. [`tools/test_machine_voice_composition.py`](tools/test_machine_voice_composition.py)
12. [`CONNECTED_FINALIZATION.md`](CONNECTED_FINALIZATION.md)
13. [`NEXT_BUILD.md`](NEXT_BUILD.md)

The obsolete first-build hold is released. Every future snapshot must still be explicitly confirmed and preserve its exact source lock and evidence boundary.
