# AXM AI-Native User Surface

The first monolith should not only describe capabilities. It should make captured **user-facing capabilities directly exercisable** from one local interface and give a machine a deterministic input path into those surfaces.

This layer is generated only after a real monolith snapshot exists. It does **not** release the current build hold and it does not capture any repository heads by itself.

## Default generated interface

The official test-week workflow turns the inspector's original dashboard into:

- `STACK_DASHBOARD.html` — factual stack/capability map;
- `OPEN_ME.html` — default **Capability Lab**;
- `AI_TEST_LAB.html` — explicit alias of the same lab;
- `USER_FACING_SURFACES.json` — machine-readable launchable browser surfaces;
- `AI_NATIVE_INPUT_PROTOCOL.json` — machine-readable input vocabulary.

So `OPEN_ME.html` starts from **use/test**, while the older capability map remains one click away.

## Capability use model

For every analyzed module, the generator maps declared/detected capabilities to any browser-facing HTML entrypoint it can ground from the captured snapshot.

A module with a launchable browser surface can be loaded inside the Capability Lab without copying or rewriting the source module.

A non-browser capability is still shown, but remains `inspect-only` until a specific execution adapter exists. The interface must not invent an executable adapter merely because a capability name exists.

## AI-native keyboard and input bus

The local lab accepts deterministic action sequences such as:

```json
{
  "surface": "axm-ghost-studio",
  "actions": [
    {"type": "tap_key", "key": "ArrowUp", "duration_ms": 120},
    {"type": "tap_key", "key": "Enter"},
    {"type": "wait", "ms": 250},
    {"type": "snapshot", "label": "after-input"}
  ]
}
```

Supported actions include:

- `tap_key`
- `key_down`
- `key_up`
- `type_text`
- `wait`
- `click`
- `click_selector`
- `focus_selector`
- `reload`
- `snapshot`

The browser UI provides common game/navigation keys directly (`WASD`, arrows, Enter, Space, Escape, R) plus a JSON action editor.

When the local server is running, a machine can also enqueue the same actions through:

```text
POST http://127.0.0.1:8765/api/command
```

The open Capability Lab polls that local queue and applies the sequence to the selected captured surface.

## User-facing visual state

A `snapshot` action records evidence from the currently loaded user-facing surface.

The harness captures:

- viewport dimensions and device pixel ratio;
- document title/path;
- focused element;
- visible DOM elements with bounding boxes;
- selected computed visual properties;
- visible text (bounded);
- form values except password fields, which are redacted;
- runtime errors/unhandled rejections observed by the harness;
- every readable `<canvas>` as an exact PNG plus SHA-256.

When the local server is active, evidence is written under:

```text
evidence/user-facing/
```

Canvas data is externalized into PNG files and the JSON evidence references those files and hashes.

This lets an AI compare user-facing states before/after an input sequence without requiring the module itself to know anything about the test harness.

## Truth boundary

The distinctions matter:

### Synthetic input is not trusted input

Browser-generated `KeyboardEvent`, `PointerEvent`, and `MouseEvent` instances keep `isTrusted == false`.

They are useful evidence for ordinary event handling, movement, navigation, controls, form logic, state transitions, and many games.

They do **not** prove browser paths that require a real trusted user activation, such as some fullscreen, audio-autoplay, clipboard, file-picker, or pointer-lock transitions.

Those remain human/browser-environment validation items when relevant.

### DOM visual state is not a whole-window screenshot

The DOM/layout capture records visible structure, geometry, selected computed styles, focus, text, and errors.

That is grounded visual-state evidence, but it is **not** pixel evidence of the complete rendered browser window.

### Canvas PNG is pixel evidence for that canvas

When `canvas.toDataURL()` succeeds, the resulting PNG is an exact capture of that canvas at that moment and is hashed when persisted.

If a canvas is tainted by inaccessible cross-origin content, capture is marked blocked rather than silently claimed.

### Launchable does not mean correct

A surface being discoverable and loadable means only that the snapshot contains a structurally launchable browser entrypoint.

Correct behavior, visual quality, composition compatibility, and product readiness still require evidence.

## Local server boundary

`tools/serve_snapshot.py` binds to `127.0.0.1` by default.

It can:

- serve the captured snapshot;
- queue AI-native browser input;
- persist user-facing evidence;
- record command completion.

It does **not** execute discovered module CLI/test commands and it does not modify source repositories.

## First-test workflow

After the growth batch is merged and the monolith build hold is deliberately released:

```text
TEST_NEXT_WEEK.cmd
        ↓
prepare exact pinned plan
        ↓
review public identity set
        ↓
build exact saved plan
        ↓
analyze stack
        ↓
generate Capability Lab
        ↓
open OPEN_ME.html through local server
        ↓
human or AI exercises user-facing capabilities
        ↓
visual/input evidence remains bound to that exact snapshot
```

This is the first user-facing execution layer. It should grow from evidence after the real stack is captured rather than assuming every non-browser capability already shares one runtime contract.
