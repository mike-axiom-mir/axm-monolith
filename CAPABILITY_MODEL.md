# AXM Assembly Capability Model

The Assembly has two separate jobs:

1. **capture the whole eligible public stack without changing source identity**;
2. **make that captured stack understandable and testable from one place**.

The second job is implemented by `tools/inspect_stack.py`.

## Why this is not a fake universal API

Most AXM repositories were not originally built against one shared interface. The Assembly therefore does not pretend they already interoperate.

It first describes what can be grounded from the captured files, then labels possible cross-module relationships by evidence strength.

## Capability evidence classes

### Native manifest

A source module may optionally contain one of:

- `AXM_MODULE.json`
- `axm-module.json`
- `.axm/module.json`

The shape is documented by `schemas/AXM_MODULE.schema.json`.

A native declaration is stronger than heuristic discovery, but **declaration is still not runtime verification**.

### Structural scan

The inspector can deterministically observe things such as:

- browser entry points;
- Python or JavaScript source;
- package scripts;
- tests;
- machine-readable schemas;
- static assets;
- obvious launch files.

These are recorded as `detected_not_executed` unless actual execution evidence exists elsewhere.

### Inference rules

For older modules without a native manifest, the inspector can use repository identity, README text, and file names to produce bounded capability leads such as creation, state, institution, simulation, game studio, assets, multiplayer, or machine voice.

These are always labelled `inferred_not_verified`.

They exist to make a large first monolith inspectable before every source repo has been adapted to a common contract.

## Connection graph

A capability may publish `provides` tokens and another capability may publish `accepts` tokens.

Example:

```text
Creation
  provides: artifact.software

Institution lane
  accepts: artifact.software
```

The Assembly can then record a candidate edge.

Possible edge states include:

```text
declared_contract_match_not_tested
structurally_possible_not_tested
inferred_candidate_not_tested
```

There is deliberately no automatic `VERIFIED` state.

A connection becomes verified only after a separate exact-composition experiment establishes that it really works.

## Composition candidates

The inspector can walk candidate edges and show short multi-module chains.

For example, a future snapshot might expose a candidate chain resembling:

```text
Institution -> Creation -> Evidence
```

That means the interfaces appear composable enough to justify an experiment. It does **not** mean the Assembly executed the workflow successfully.

## Human test queue

The Assembly specifically tries to reduce the amount of repository archaeology Mike has to do.

Modules with human-value surfaces such as games, visible browser interfaces, audio, or simulations are pulled into `HUMAN_TEST_QUEUE.json` with the relevant entrypoints when they can be identified.

The intention is that machine-verifiable work stays machine-verifiable while the human is pointed toward the small set of places where human observation is actually valuable.

## Automated test queue

Existing test commands and safe static probes are discovered into `AUTOMATED_TEST_QUEUE.json`.

They are **not run automatically during assembly**.

Arbitrary project tests can execute code, access files, start servers, or have assumptions about their environment. The first monolith should expose those commands before deciding which ones are appropriate to execute.

## Offline output

Every enabled future build automatically generates:

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

`OPEN_ME.html` is dependency-free and can be opened locally. It is the simplest human-facing view of the assembled stack.

## Querying after assembly

Search the analyzed stack:

```bash
python tools/inspect_stack.py query <build-dir> game
python tools/inspect_stack.py query <build-dir> state
python tools/inspect_stack.py query <build-dir> creation
```

Ask whether the candidate graph contains a route between two modules:

```bash
python tools/inspect_stack.py route <build-dir> axm-universal-creation axm-institution-fabric
```

A returned route is labelled `candidate_route_not_verified` until separately exercised.

## Future growth

The first snapshot will teach us which inferred interfaces are real, which are wrong, and which shared primitives appear repeatedly.

Only then should AXM progressively replace heuristics with native module manifests, adapters, and tested cross-module protocols.

The Assembly is meant to discover the connector language from the real stack rather than imposing an imaginary universal architecture before seeing the whole system together.
