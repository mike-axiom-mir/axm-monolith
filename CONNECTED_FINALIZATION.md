# Connected finalization

AXM Monolith now owns the plumbing and packaging gate that used to be performed manually
after a snapshot was assembled.

## What every build does automatically

`tools/assemble.py build` now performs, in order:

1. exact-SHA public repository materialization;
2. aggregate capability analysis;
3. exact declared-leaf inventory with file and JSON-pointer provenance;
4. candidate pipeline export;
5. source-declared callable registry generation;
6. installation of the bounded Python/JavaScript invocation and evidence-ledger runtimes;
7. installation of one local front door and direct workflow/capability shortcuts.

This makes the machinery available. It does not claim that every declaration is callable.

## One-command evidence-gated package

```bash
python tools/finalize_connected_snapshot.py \
  --snapshot ../axm-monolith-builds/<snapshot> \
  --output-zip ../axm-monolith-builds/AXM_Connected_Monolith.zip \
  --folder-name AXM_Connected_Monolith \
  --confirm-finalize
```

The command re-runs plumbing before packaging, writes a file-by-file SHA-256 receipt, rejects
symlinks and unsafe archive paths, and refuses to overwrite an existing ZIP.

## Require native callable execution

Supply an explicit invocation plan:

```json
{
  "schema": "axm.monolith.invocation-plan/v0.1",
  "invocations": [
    {
      "address": "module::capability",
      "request": {
        "schema": "axm.callable-invocation-request/v0.1",
        "args": []
      },
      "allow_execution": true,
      "required": true
    }
  ]
}
```

Then run:

```bash
python tools/finalize_connected_snapshot.py \
  --snapshot ../axm-monolith-builds/<snapshot> \
  --invocation-plan invocation-plan.json \
  --require-address module::capability \
  --output-zip ../axm-monolith-builds/AXM_Connected_Monolith.zip \
  --folder-name AXM_Connected_Monolith \
  --confirm-finalize
```

Required calls must produce valid source-bound receipts in the execution ledger. Unsupported
runtimes, missing input, timeouts, invalid results, changed source bytes, and identity mismatches
remain blocking evidence.

## Require the Blackline 3D workflow

```bash
python tools/finalize_connected_snapshot.py \
  --snapshot ../axm-monolith-builds/<snapshot> \
  --blackline-output outputs/blackline-3d \
  --blackline-reference /path/to/blackline-reference.png \
  --output-zip ../axm-monolith-builds/AXM_Connected_Monolith.zip \
  --folder-name AXM_Connected_Monolith \
  --confirm-finalize
```

The workflow uses captured Universal Creation and Game Assets source code and binds the result
to the captured Ghost Studio charter. Packaging stops unless the workflow reaches
`EXECUTED_END_TO_END_AND_STRUCTURALLY_ACCEPTED`. The output must stay inside the snapshot;
packaging re-runs its structural review so a stale receipt cannot cover moved or altered GLBs.
A rejected attempt is retained and can be
exercised in testing with `--exercise-rejection` through `tools/ghost_studio_pipeline.py`.

## Truth boundary

- Aggregate labels describe broad surfaces.
- Declared leaf IDs are exact source declarations with provenance.
- Candidate graph edges describe possible composition.
- Native callable declarations describe bounded entry contracts.
- Accepted execution receipts prove only the exact calls or workflow they name.

None of those layers silently upgrades another. A connected package can prove selected routes
while still containing many explicitly unbound capabilities.
