# Machine Voice real-state bridge v0.1

`axm-monolith` can now export one piece of its **actual checked-in state** into the strict Machine Voice snapshot protocol without assembling or copying another repository.

## First grounded source

The first bridge intentionally uses a state that already exists in this repository:

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

When `build_enabled` is `true`, it emits nothing. Silence is a valid result.

The exporter does **not** claim the hold is good, bad, important, anomalous, novel, or mistaken.

## Export current monolith state

From the `axm-monolith` repository root:

```bash
python tools/export_machine_voice_state.py \
  --output build/MACHINE_VOICE_NOTICE.json
```

The current checked-in `config/assembly.json` has `build_enabled: false`, so the current repository state should produce a notice snapshot.

The snapshot schema id is:

```text
axm-machine-voice/notice-snapshot/0.1
```

## Local cross-repository proof

When `axm-monolith` and `axm-machine-voice` are both available locally, process the exported snapshot with the real Machine Voice runtime:

```bash
python tools/export_machine_voice_state.py \
  --output build/MACHINE_VOICE_NOTICE.json

python ../axm-machine-voice/machine_voice.py snapshot \
  build/MACHINE_VOICE_NOTICE.json \
  --active-ref activity:assembly-control \
  --journal build/MACHINE_VOICE_COMMUNICATION.jsonl
```

Expected current result:

```text
emitted packet kind: notice
FloorVoice: I noticed something.
```

That expected result is **not yet claimed cross-repository verified by this repository alone**. The monolith CI intentionally does not fetch/capture repository mains. Local composition (or a later explicitly staged assembly snapshot containing both modules) must perform that final runtime proof.

## What CI does prove

`tests/test_machine_voice_state_export.py` reads the real checked-in `config/assembly.json` and proves that:

- the current explicit hold produces a strict `notice-snapshot/0.1` object;
- the source and active-context contract are explicit;
- the notice contains the exact required signal fields and no extra interpretation fields;
- an enabled build produces silence;
- a false build state without a hold reason fails closed;
- changing the hold reason changes its semantic evidence identity.

## Evidence identity

Machine Voice semantic fingerprints intentionally exclude event ids, so the exporter also includes a stable hash of the current hold reason in the subject/evidence references. If the hold reason changes, the grounded notice semantics change too rather than being silently suppressed as the previous hold.

The original hold reason text remains in `config/assembly.json`; the notice snapshot references it rather than copying free-form prose into FloorVoice.

## Truth boundary

This bridge proves a state-contract handoff, not a thought, intention, or autonomous conclusion.

It does not:

- execute Machine Voice inside monolith CI;
- authenticate that another repository has not changed after this contract was written;
- turn `build_enabled: false` into a failure, warning, recommendation, or problem claim;
- enable monolith assembly;
- capture repository mains;
- grant merge, CANON, execution, device, network, or installation authority.

The final cross-repository runtime check belongs to a local/staged monolith composition where both exact module versions are present.
