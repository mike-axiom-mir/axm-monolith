# AXM Monolith — Invariant Lab Evidence Consumer v0.1

## Purpose

Monolith can consume one machine-readable AXM Invariant Lab counterexample packet as **external bounded evidence** without importing Invariant Lab as an authority and without rewriting the packet into stronger semantics.

This is deliberately narrower than integrating invariant results into pipeline ranking or execution. The first consumer only validates, preserves, hashes, and summarizes the packet.

## Donor pin

Source repository: `mike-axiom-mir/axm-invariant-lab`

Pinned donor main at integration time:

- commit: `f3aab96f448c67fa79c1277b00f374707c4577f7`
- packet path: `evidence/first_counterexample_receipt.json`
- packet blob: `02eeddfd12351ff6b7647bc412db3695ee45e5b3`
- schema path: `COUNTEREXAMPLE_PACKET.schema.json`
- schema blob: `cc9f1fde4855a56557ad6338c7595a99fc71cb21`
- source schema id: `axm.invariant-lab.counterexample/v0.1`

The checked-in fixture is byte-for-byte the pinned donor packet at that boundary.

## Consumer behavior

`tools/import_invariant_packet.py`:

1. requires the exact v0.1 packet field set;
2. preserves `FAIL` or `HOLD` rather than translating either into Monolith pipeline truth;
3. rejects `PASS` because the donor's counterexample packet contract does not define PASS;
4. rejects unexpected fields rather than guessing future semantics;
5. requires every donor authority field to remain explicitly `false`;
6. records a SHA-256 of the exact input bytes;
7. emits a deterministic evidence-only summary;
8. never mutates `PIPELINE_GRAPH.json`, `PIPELINE_CANDIDATES.json`, module source, assembly state, or donor files.

Example:

```bash
python tools/import_invariant_packet.py fixtures/invariant-lab-counterexample-v0.1.json
```

## Truth boundary

A successful import means only that one packet conforms to the exact bounded v0.1 consumer contract implemented here.

It does **not** mean:

- the modeled fault exists in Monolith;
- the Invariant Lab model proves Monolith behavior;
- a Monolith pipeline is verified or invalidated;
- the packet authorizes action;
- future packet schema versions are compatible;
- cross-repo evidence rung 6 is automatically earned by Invariant Lab.

This is one real external AXM consumer. A second materially different external consumer is still required before Invariant Lab can honestly claim the seed's two-system CROSS-REPO rung.
