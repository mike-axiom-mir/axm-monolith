# Blackline Relay reference-kit build

`tools/ghost_studio_reference_kit.py` turns the supplied Blackline Relay environment sheet into a bounded modular 3D proposal through one installed AXM monolith snapshot.

It builds nine canonical reference assets plus one conduit state variant:

- online and offline relays;
- modular relay base;
- online conduit segment plus an offline state variant;
- 1 m floor panel;
- 2 m wall panel;
- closed door;
- 2 m platform with railings;
- 2 m ramp.

Each delivery includes meter-scale source geometry, embedded PBR materials in a self-contained GLB, a Game Asset Forge-compatible delivery receipt, a separate simple collision GLB, four software previews, and an asset receipt. The full generated material library includes base color, normal, roughness, metallic, height, AO, and packed ORM maps.

```bash
python3 tools/ghost_studio_reference_kit.py \
  --build ../builds/blackline-reference-monolith \
  --reference ../upload/01-1000000478.png \
  --output ../builds/blackline-relay-3d-kit-v0.1 \
  --confirm-create
```

This build does not silently install the assets into Ghost Studio or inherit gameplay/route evidence. Engine import, performance, art approval, collision fit, studio adoption, and canon remain explicit downstream checks.
