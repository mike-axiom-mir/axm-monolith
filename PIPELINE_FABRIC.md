# AXM Monolith Pipeline Fabric

## Purpose

The Monolith already inventories modules, capabilities, candidate interface edges, and short composition chains. Pipeline Fabric turns that snapshot into a reusable machine-readable **possibility map**.

Its question is:

> Given the capabilities visible in this exact assembled stack, what bounded multi-capability pipelines appear possible, what outputs can they lead to, and where are the missing seams?

This belongs in `axm-monolith` because The Assembly is the place that can see the whole captured public stack at once. It does **not** make Monolith the permanent live execution floor.

## What it produces

After `STACK_ANALYSIS.json` exists:

```bash
python tools/pipeline_fabric.py export <build-dir>
```

writes:

```text
PIPELINE_FABRIC.json
PIPELINE_GRAPH.json
PIPELINE_CANDIDATES.json
PIPELINE_GAPS.json
```

These files are deliberately portable so another AXM project can consume the result without importing Monolith internals.

## Goal query

Ask which candidate pipelines can end in a specific provided token:

```bash
python tools/pipeline_fabric.py goal <build-dir> artifact.game-build
python tools/pipeline_fabric.py goal <build-dir> evidence
python tools/pipeline_fabric.py goal <build-dir> interface.machine-voice
```

A returned path is a **candidate path**, not an executed plan.

## Gap query

```bash
python tools/pipeline_fabric.py gaps <build-dir>
```

The gap report separates:

- `missing_internal_provider` — a capability accepts a token that no current capability appears to provide;
- `external_input_not_internal_gap` — inputs such as objectives, questions, messages, or scenarios that may legitimately enter from outside the stack;
- `currently_unconsumed_output` — a provided token with no current consumer;
- `lexical_adapter_candidate_not_verified` — two tokens look related enough to justify an adapter experiment, but semantic compatibility has not been established.

The final category is intentionally weak evidence. Shared words do not prove compatible semantics.

## Refresh

For an already materialized Monolith build:

```bash
python tools/pipeline_fabric.py refresh <build-dir>
```

re-runs the existing stack inspector first, then regenerates Pipeline Fabric outputs.

## Reuse boundary

Future AXM systems may consume the exported files as a capability:

```text
STACK_ANALYSIS.json
        ↓
Pipeline Fabric
        ↓
capability-level graph
candidate pipelines
goal queries
gap / adapter leads
        ↓
WALMI / Mesh / Open Floor / another future consumer
```

A consumer must preserve the evidence labels and truth boundaries. It must not silently convert:

```text
candidate -> verified
lexical similarity -> semantic compatibility
route -> permission
possibility -> execution
```

## Relationship to an Open Floor

Pipeline Fabric answers:

> **What can probably connect, and what remains missing or unverified?**

A future Open Capability Floor would answer:

> **Which grounded capabilities are currently available to call, under what permissions and state?**

Those are deliberately different responsibilities. Pipeline discovery starts here because Monolith can see the stack. Live execution can be extracted later if evidence shows a separate floor is useful.

## Roots

**Truth** — candidate, structural, inferred, and verified evidence stay distinct.

**Agency / non-domination** — discovery creates no automatic execution, installation, merge, CANON, device, or network authority.

**Continuity** — module identity and capability identity remain explicit in every pipeline node.

**Wisdom before speed** — missing seams remain visible; the tool proposes bounded experiments instead of auto-generating integration glue and pretending it works.

## Current evidence

The v0.1 implementation has deterministic fixture tests for:

- capability-level graph derivation;
- preservation of edge evidence;
- multi-hop pipeline discovery;
- weakest-edge status propagation;
- goal-token querying;
- external-input versus internal-gap separation;
- lexical adapter candidates remaining explicitly unverified;
- byte-deterministic export on identical input.

This is fixture evidence for the pipeline machinery. It is not yet evidence that a real full-stack Monolith snapshot contains useful or executable pipelines.
