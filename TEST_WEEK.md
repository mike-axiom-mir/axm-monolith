# AXM Monolith — First Test Week

This is the practical runbook for the first full-stack experiment after the growth merge/reconciliation batch is finished.

The goal is to make the first test easy without weakening the source, privacy, provenance, or truth boundaries.

## Before test day

Leave `config/assembly.json` with `build_enabled: false` until the chosen public repository heads are actually ready to capture.

Do not prepare a plan early and call it next week's state. The plan is the snapshot moment.

When the growth batch is ready, deliberately release the hold first. The test-drive tooling will not release it on its own.

## The simple route

From the `axm-monolith` repository, run:

```bash
python tools/test_drive.py
```

This opens a guided menu.

Use it in this order:

1. **Preflight** — checks Python, Git, free disk, config boundary, and whether the hold has been released. This does not capture repository heads.
2. **Prepare exact candidate plan** — discovers the eligible public AXM repos, applies exclusions, pins exact default-branch SHAs, and writes `CANDIDATE_PLAN.json` plus `PLAN_SUMMARY.md` in the test workspace.
3. **Review the plan** — make sure the included public repos are really the intended AXM public identity set. The collaboration platform and monolith must be absent.
4. **Build saved plan + analyze** — type the explicit `BUILD` confirmation. The build uses the saved plan exactly; it does **not** refresh repository heads after review.
5. **Open dashboard** — opens `snapshot/OPEN_ME.html`.
6. **Record human test results** — the guided queue shows only modules where human observation is currently useful and stores results beside this exact snapshot.

Default workspace:

```text
../axm-monolith-test/
  CANDIDATE_PLAN.json
  PLAN_SUMMARY.md
  snapshot/
    axm-stack.lock.json
    MONOLITH_MANIFEST.json
    OPEN_ME.html
    STACK_REPORT.md
    STACK_ANALYSIS.json
    CAPABILITY_REGISTRY.json
    CONNECTION_GRAPH.json
    COMPOSITION_CANDIDATES.json
    HUMAN_TEST_QUEUE.json
    AUTOMATED_TEST_QUEUE.json
    HUMAN_TEST_RESULTS.json      # appears after guided human testing
    modules/
      ...
```

## Why the plan is frozen before building

The first assembler version could resolve repository heads again during the later build step. That creates a small but real race: a repo could change after you reviewed the plan but before materialization.

The guided test drive avoids that. It creates one exact plan first and later builds from those exact pinned SHAs.

So:

```text
reviewed plan == materialized source set
```

not:

```text
reviewed plan -> silently refreshed heads -> different build
```

## Human testing

The Assembly does not require you to test everything manually.

The generated human queue prioritizes things such as games, browser interfaces, simulations, audio/visual surfaces, and inferred capability descriptions that benefit from a person actually looking at them.

The guided session records one of:

```text
pass
fail
uncertain
skipped
```

plus optional notes.

Those records belong to the exact snapshot. A later monolith must not silently inherit them if source commits changed.

## Automated tests

`AUTOMATED_TEST_QUEUE.json` is an inventory, not an execution order.

The first full-stack test deliberately does **not** execute every discovered repository command automatically. Some repos may contain expensive, environment-specific, networked, destructive, or simply stale scripts.

After the first snapshot, the next evidence step is to classify discovered commands into bounded execution classes and run the safe ones against the pinned snapshot.

## What to look at first in OPEN_ME.html

Do not start by trying to understand every file.

Look at:

1. module count / total files / total size;
2. capability registry;
3. modules with native AXM manifests versus inferred capability only;
4. candidate connection graph;
5. strongest candidate composition chains;
6. uncertainties;
7. human-test queue;
8. discovered automated/static checks.

Then ask practical questions such as:

```text
What can the stack already make?
What can it simulate?
What can it test?
Which systems appear able to feed one another?
Where are we duplicating the same primitive?
Which connection would unlock the largest new capability if proven?
What currently needs a human rather than another machine check?
```

## First-test truth boundary

The first monolith is a **capability discovery and integration experiment**.

A beautiful graph is not proof that every edge works.

A detected capability is not automatically a mature capability.

A human `pass` means that person observed the requested behavior on that exact snapshot; it does not mean production quality.

A `fail` is useful evidence.

An `uncertain` result is valid evidence.

A module that cannot currently run is still part of the truthful snapshot if it was eligible and captured; mark the blocker rather than deleting it from the story.

## Stop condition

The first test week is successful when we can answer, from one pinned public-stack snapshot:

- what is actually present;
- what independently works;
- what appears connectable;
- which compositions have evidence versus only inference;
- what fails;
- what is uncertain;
- what requires human testing;
- what next connector/adaptor would unlock the most continuation value.

Do not try to make the entire stack perfect during the first test. The first monolith's job is to expose reality clearly enough that the next integration work becomes obvious.
