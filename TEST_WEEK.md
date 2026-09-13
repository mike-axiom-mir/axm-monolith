# AXM Monolith — First Test Week

This is the practical runbook for the first full-stack experiment after the growth merge/reconciliation batch is finished.

The goal is to make the first test easy without weakening source identity, privacy, provenance, or truth boundaries.

## Before test day

`config/assembly.json` now permits deliberate builds. Do not prepare a plan early and call it next week's state: **the plan is the snapshot moment**. Every materialization still requires explicit confirmation.

## The simple route

On Windows:

```text
TEST_NEXT_WEEK.cmd
```

On Linux/macOS:

```bash
./test-next-week.sh
```

Both now launch:

```bash
python tools/test_week_plus.py
```

Use the menu in this order:

1. **Preflight** — checks Python, Git, free disk, selection boundary, and whether the hold has been released. It does not capture repository heads.
2. **Prepare exact candidate plan** — discovers eligible public AXM repos, applies exclusions, pins exact default-branch SHAs, and writes `CANDIDATE_PLAN.json` plus `PLAN_SUMMARY.md`.
3. **Review the plan** — confirm the included public repos are the intended AXM public identity set. The collaboration platform and monolith must be absent.
4. **Build exact saved plan + analyze + generate capability lab** — type the explicit `BUILD` confirmation. The build uses the reviewed plan exactly and does not refresh heads.
5. **Open capability lab** — launches the captured stack locally on `127.0.0.1` and opens `OPEN_ME.html`.
6. **Exercise user-facing capabilities** — manually or through the AI-native input queue.
7. **Record human test results** where human observation is still useful.

## Default workspace

```text
../axm-monolith-test/
  CANDIDATE_PLAN.json
  PLAN_SUMMARY.md
  snapshot/
    axm-stack.lock.json
    MONOLITH_MANIFEST.json

    OPEN_ME.html                 # default Capability Lab
    AI_TEST_LAB.html             # same user-facing lab
    STACK_DASHBOARD.html         # original factual stack map
    STACK_REPORT.md
    STACK_ANALYSIS.json
    CAPABILITY_REGISTRY.json
    CONNECTION_GRAPH.json
    COMPOSITION_CANDIDATES.json
    HUMAN_TEST_QUEUE.json
    AUTOMATED_TEST_QUEUE.json
    USER_FACING_SURFACES.json
    AI_NATIVE_INPUT_PROTOCOL.json

    HUMAN_TEST_RESULTS.json      # appears after guided human testing
    evidence/
      user-facing/               # appears when AI/user-facing evidence is saved

    modules/
      ...
```

## Why the plan is frozen before building

A repo can move between plan review and materialization.

The test-week flow avoids that race:

```text
reviewed CANDIDATE_PLAN.json
          ==
materialized source set
```

not:

```text
reviewed plan
    -> silently refreshed heads
    -> different build
```

Human and machine evidence therefore remain attached to an exact source set.

## Capability Lab

After the build, the generated default interface is no longer only a capability report.

`OPEN_ME.html` becomes a **use/test surface** for browser-facing capabilities.

It provides:

- searchable capabilities and modules;
- launchable browser entrypoints from captured modules;
- a built-in AI-native keyboard/input panel;
- JSON action scripts;
- direct `WASD`, arrows, Enter, Space, Escape and R controls;
- selector/click/focus actions;
- user-facing visual-state capture;
- links back to the factual stack dashboard and report.

See [`AI_NATIVE_USER_SURFACE.md`](AI_NATIVE_USER_SURFACE.md).

## AI-native testing

With the local lab server running, a machine can send a bounded user-facing sequence to:

```text
POST http://127.0.0.1:8765/api/command
```

Example:

```json
{
  "surface": "axm-ghost-studio",
  "actions": [
    {"type": "tap_key", "key": "ArrowUp", "duration_ms": 120},
    {"type": "wait", "ms": 250},
    {"type": "snapshot", "label": "after-up"}
  ]
}
```

The open Capability Lab consumes the sequence and applies it to that captured browser surface.

This gives an AI a deterministic input path through the **same user-facing interface** rather than only testing hidden functions.

## Visual-state evidence

A `snapshot` records bounded user-facing evidence such as:

- viewport and focus state;
- visible DOM geometry;
- selected computed visual styles;
- visible text;
- observed runtime errors;
- readable canvas pixels as exact PNG files with SHA-256.

Evidence is written only beside the exact snapshot under:

```text
evidence/user-facing/
```

A DOM visual-state record is **not** a full-browser screenshot. A readable canvas PNG is pixel evidence for that canvas only. The interface states those boundaries explicitly.

## Synthetic-input truth boundary

The AI-native keyboard uses browser-generated keyboard/pointer events.

Those events have `isTrusted == false`.

They are useful for ordinary user-facing controls, menus, games, navigation, text entry, state transitions, and many UI behaviors.

They do not prove flows that require a real trusted user gesture, such as some fullscreen, autoplay, file-picker, clipboard, or pointer-lock transitions. Those remain human/browser-environment validation items when relevant.

## Human testing

The Assembly does not require one person to test everything.

The generated human queue prioritizes things such as games, browser interfaces, simulations, audio/visual surfaces, and inferred capability descriptions where human observation adds evidence.

The guided session records:

```text
pass
fail
uncertain
skipped
```

plus optional notes.

Those records belong to the exact snapshot. A later monolith must not silently inherit them if source commits changed.

## Automated tests

`AUTOMATED_TEST_QUEUE.json` is still an inventory, not a blind execution order.

The first full-stack test deliberately does **not** execute every discovered repository command automatically. Some repos may contain expensive, networked, environment-specific, destructive, or stale scripts.

After the first real snapshot, classify discovered commands into bounded execution classes and then automate the safe categories from evidence.

## What to inspect first

Do not start by reading every file.

Look at:

1. module count / total files / total size;
2. capability registry;
3. native manifests versus inferred capability only;
4. candidate connection graph;
5. strongest candidate composition chains;
6. launchable user-facing surfaces;
7. visual/input evidence from the Capability Lab;
8. uncertainties;
9. human-test queue;
10. discovered automated/static checks.

Then ask practical questions such as:

```text
What can the stack already make?
What can it simulate?
What user-facing capabilities can machine input actually exercise?
Which visual states change under input?
Which systems appear able to feed one another?
Where are we duplicating the same primitive?
Which connection would unlock the largest new capability if proven?
What currently needs a human rather than another machine check?
```

## First-test truth boundary

The first monolith is a **capability discovery and integration experiment**.

A beautiful graph is not proof that every edge works.

A detected capability is not automatically mature.

A synthetic-input pass is not proof of a trusted-user-activation path.

A captured DOM state is not automatically a visual-quality judgment.

A human `pass` means that person observed the requested behavior on that exact snapshot; it does not mean production quality.

A `fail` is useful evidence.

An `uncertain` result is valid evidence.

A module that cannot currently run is still part of the truthful snapshot if it was eligible and captured; record the blocker rather than deleting it from the story.

## Stop condition

The first test week is successful when one pinned public-stack snapshot can answer:

- what is actually present;
- what independently works;
- what capabilities can be exercised through user-facing surfaces;
- what visual/user-facing state evidence exists;
- what appears connectable;
- which compositions have evidence versus only inference;
- what fails;
- what is uncertain;
- what requires human testing;
- what next connector/adapter would unlock the most continuation value.

Do not try to make the entire stack perfect during the first test. The first monolith's job is to expose reality clearly enough that the next integration work becomes obvious.
