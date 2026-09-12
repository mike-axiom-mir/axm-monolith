# Machine Voice real-state bridge v0.2

`axm-monolith` can export one piece of its **actual checked-in state** into the strict Machine Voice snapshot protocol, and can now run the first local cross-repository composition proof in one command when `axm-machine-voice` is physically available.

## First grounded source

The first bridge intentionally uses state that already exists in this repository:

```text
config/assembly.json
        ↓
explicit build_enabled boolean
        ↓
rule: assembly-build-hold-active-v0.1
        ↓
axm-machine-voice/notice-snapshot/0.1
```

When `build_enabled` is `false` and a non-empty `hold_reason` exists, the exporter emits a grounded generic notice snapshot.

When `build_enabled` is `true`, it emits nothing. Silence is valid.

The exporter does **not** claim the hold is good, bad, important, anomalous, novel, failed, or mistaken.

## Export only

From the `axm-monolith` repository root:

```bash
python tools/export_machine_voice_state.py \
  --output .generated/machine-voice-composition/MACHINE_VOICE_NOTICE.json
```

The current checked-in `config/assembly.json` has `build_enabled: false`, so the current repository state should produce a notice snapshot.

Snapshot schema:

```text
axm-machine-voice/notice-snapshot/0.1
```

## One-command local composition proof

Default local layout:

```text
parent/
  axm-monolith/
  axm-machine-voice/
```

Run from `axm-monolith`:

```bash
python tools/test_machine_voice_composition.py
```

The runner performs this exact path:

```text
real config/assembly.json
        ↓
Monolith exporter
        ↓
MACHINE_VOICE_NOTICE.json
        ↓
real ../axm-machine-voice/machine_voice.py
        ↓
Machine Voice machine channel
        ↓
MACHINE_VOICE_COMMUNICATION.jsonl
        ↓
MACHINE_VOICE_COMPOSITION_RESULT.json
```

Generated local evidence is written under:

```text
.generated/machine-voice-composition/
```

That directory is already ignored by git.

### Healthy result states

First run against the current held assembly state should produce:

```text
verified_fresh_emission
```

with a Machine Voice packet whose kind is:

```text
notice
```

Machine Voice maps that kind to the fixed FloorVoice phrase:

```text
I noticed something.
```

The composition runner verifies the actual machine packet kind and producer. It does **not** separately re-execute the browser/FloorVoice mapping, so its result file labels that distinction explicitly.

A later run with the same persistent journal may produce:

```text
verified_duplicate_suppression
```

That is also a successful composition result: the real Machine Voice process was reached and correctly refused to speak the same semantic event twice.

If Monolith's exact exporter rule legitimately produces no snapshot, the runner reports:

```text
not_exercised_no_snapshot
```

That is valid silence, not runtime verification.

### Force a fresh emission proof

The default preserves the local proof journal. To explicitly remove **only this proof journal** before running:

```bash
python tools/test_machine_voice_composition.py --reset-journal
```

This option does not touch any other file.

### Non-sibling checkout

If Machine Voice lives somewhere else:

```bash
python tools/test_machine_voice_composition.py \
  --machine-voice-root /path/to/axm-machine-voice
```

## What repository CI proves

CI still does **not** fetch or copy the real Machine Voice repository.

It proves two bounded things:

1. `tests/test_machine_voice_state_export.py` reads the real checked-in `config/assembly.json` and proves the Monolith produces the exact strict notice snapshot expected for the current hold.
2. `tests/test_machine_voice_local_composition.py` drives the one-command orchestration against a fake external process and proves process invocation, machine JSON validation, journal handling, fresh-emission handling, duplicate-suppression handling, silence behavior, and fail-closed behavior.

Therefore CI evidence remains:

```text
orchestrator fixture tested
real cross-repository runtime requires local/staged run
```

Only a run with the actual `axm-machine-voice` checkout can upgrade this exact connection to local runtime evidence.

## Evidence identity

Machine Voice semantic fingerprints intentionally exclude event ids, so the exporter includes a stable hash of the current hold reason in subject/evidence references. If the hold reason changes, the grounded notice semantics change rather than being silently suppressed as the previous hold.

The original hold reason text remains in `config/assembly.json`; the notice snapshot references it instead of copying free-form prose into FloorVoice.

## Truth boundary

This bridge is state handoff and explicit composition evidence, not a thought, intention, or autonomous conclusion.

It does not:

- release or bypass the assembly hold;
- capture repository mains inside CI;
- infer importance, failure, anomaly, recommendation, goodness, or badness from the hold;
- make a fake-process CI test count as real Machine Voice runtime verification;
- make one successful Machine Voice bridge verify unrelated AXM module composition;
- grant merge, CANON, execution, device, network, or installation authority.

A successful real local run means only:

> this exact Monolith state exporter successfully crossed the real Machine Voice machine-channel boundary on this local/staged checkout and produced either a fresh grounded notice or correct duplicate suppression.
