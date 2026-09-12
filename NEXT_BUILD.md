# NEXT BUILD — First On-Demand Assembly

## HOLD

**Not yet.**

The first assembly still waits until Mike explicitly says the current growth merge/reconciliation batch is ready enough to capture.

`config/assembly.json` currently has:

```json
"build_enabled": false
```

That is a hard code-enforced hold. No current main-state monolith has been generated.

## What is ready while we wait

The assembler can already perform the future capture, and the stack inspector is now ready to turn the captured repos into one inspectable capability surface.

When a future build is enabled, the same build command automatically produces:

- a reproducible exact-SHA source lock;
- namespaced source modules;
- per-module structural profiles;
- a capability registry;
- candidate interface graph;
- candidate multi-module composition chains;
- human-test queue;
- discovered automated/static-test queue;
- `STACK_REPORT.md`;
- **`OPEN_ME.html`**, the dependency-free local dashboard Mike can open directly.

No discovered project test is auto-executed during assembly. The first snapshot should expose the test surface before deciding which arbitrary project code is appropriate to execute.

## When the hold is released

### Phase 0 — deliberately enable the moment

Only after the growth merge/reconciliation pass is considered ready, change:

```json
"build_enabled": false
```

to:

```json
"build_enabled": true
```

Do not make that change early merely because the tooling is ready.

### Phase 1 — discovery

Run:

```bash
python tools/assemble.py discover
```

Check:

- only `mike-axiom-mir` repos are eligible;
- every eligible repo is public;
- private repos are absent even if credentials can see them;
- the collaboration platform is excluded;
- `axm-monolith` is excluded;
- no unexpected public repo is being pulled into the AXM identity set.

If an unexpected public repo appears, add an explicit exclusion before building.

### Phase 2 — exact plan

Run:

```bash
python tools/assemble.py plan > first-plan.json
```

Review the exact repository list and pinned SHAs.

The plan itself is evidence of the requested moment. Do not silently refresh it and pretend it is the same snapshot.

### Phase 3 — materialize + analyze

After the plan is accepted:

```bash
python tools/assemble.py build \
  --output ../axm-monolith-builds/<timestamp-or-label> \
  --confirm-build
```

The build automatically performs the deterministic inspection pass.

Expected top-level output:

```text
<output>/
  OPEN_ME.html
  STACK_REPORT.md
  STACK_ANALYSIS.json
  CAPABILITY_REGISTRY.json
  CONNECTION_GRAPH.json
  COMPOSITION_CANDIDATES.json
  HUMAN_TEST_QUEUE.json
  AUTOMATED_TEST_QUEUE.json
  axm-stack.lock.json
  MONOLITH_MANIFEST.json
  INVENTORY.md
  analysis/modules/
  modules/
```

### Phase 4 — Mike opens one file

Open:

```text
OPEN_ME.html
```

That dashboard should show, from the exact captured snapshot:

- every assembled module;
- detected/declared capabilities;
- evidence class for those capability claims;
- entrypoints and test commands;
- candidate cross-module interfaces;
- candidate composition chains;
- known module-level uncertainty;
- the short queue of places where human observation is useful.

This is the simplest answer to: **"What does the entirety currently look capable of?"**

### Phase 5 — query the stack

Examples:

```bash
python tools/inspect_stack.py query <build-dir> game
python tools/inspect_stack.py query <build-dir> state
python tools/inspect_stack.py query <build-dir> creation
```

Candidate route between two modules:

```bash
python tools/inspect_stack.py route <build-dir> <module-a> <module-b>
```

Returned routes are explicitly labelled unverified until exercised.

### Phase 6 — first truth pass

Before inventing cross-stack magic, measure:

- repository count;
- file count and disk footprint;
- runtimes/languages;
- local entrypoints;
- tests present;
- capability declarations vs structural detections vs inferences;
- duplicate concepts;
- incompatible assumptions;
- modules that cannot be exercised on current hardware/environment.

### Phase 7 — composition experiments

Use the graph and candidate chains to choose a few high-value combinations.

A graph edge means **worth testing**, not **already working**.

Every successful composition should gain its own evidence. Every failed one should remain a visible failure instead of being silently normalized away.

### Phase 8 — return repairs upstream

The generated monolith is not the replacement development branch for every module.

When a real source problem is exposed, repair/propose it in the owning source repository and later generate a new monolith snapshot.

## v0 success condition

The first real snapshot is successful when one explicitly requested moment can be reproduced and Mike can open one local dashboard that honestly answers:

- what is here;
- what each part appears or declares it can do;
- which parts appear connectable;
- which compositions are only hypotheses;
- what can be tested automatically;
- where human testing matters;
- what remains unknown.

Do not claim full-stack interoperability merely because the dashboard is impressive.
