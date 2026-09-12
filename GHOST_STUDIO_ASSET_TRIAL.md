# Ghost Studio Asset Trial

This experiment turns a monolith capability-route candidate into one bounded
execution proof without flattening or editing source modules.

It requires a completed AXM monolith snapshot containing:

- `axm-ghost-studio` as the consumer and design-boundary source;
- `axm-universal-creation` for the structured visual recipe and generated 2D
  material/texture/decal evidence;
- `Axm-game-assets` for original rigid geometry, PBR packaging, GLB delivery,
  software diagnostic previews, and independent receipt validation.

Run it explicitly:

```bash
python tools/ghost_studio_asset_trial.py \
  --build ../axm-monolith-builds/<snapshot> \
  --output ../axm-monolith-builds/<snapshot>-ghost-assets \
  --confirm-create
```

Open `OPEN_ASSET_TRIAL.html` in the output directory. The output remains a
proposal/test artifact. It does not install assets into Ghost Studio, mutate a
source repository, grant aesthetic approval, or prove that every monolith
capability executed.
