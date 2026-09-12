# AXM Monolith — One-Click Launch

A completed monolith snapshot should be usable by someone who does not understand GitHub, repository layout, runtimes, or AXM internals.

## After the first snapshot exists

### Windows

Double-click:

```text
START_AXM.cmd
```

### Linux / macOS

Run:

```bash
./START_AXM.sh
```

The generated launcher starts the local snapshot server and opens:

```text
OPEN_ME.html
```

That page is the Capability Lab / front door for the whole captured stack.

## What “launch the entirety” means

It means **launch one front door that can see and use the entire captured stack**.

It deliberately does **not** mean starting every independent module process simultaneously.

The default model is:

```text
one click
   ↓
local AXM front door
   ↓
whole capability registry + stack map + user-facing surfaces
   ↓
activate the selected capability/module on demand
```

This keeps the monolith newbie-friendly while avoiding unnecessary RAM/CPU use and avoiding false assumptions that every repository runtime is already safe to execute together.

## First-time versus later use

At repository root, the existing `TEST_NEXT_WEEK.cmd` / `test-next-week.sh` are now smart launchers:

- if no completed snapshot exists, they open the guided first-build/test flow;
- if a completed snapshot with its generated launcher exists, they launch that snapshot directly.

So after the first successful build, the normal experience becomes one click.

## Local boundary

The generated launcher binds to `127.0.0.1` by default and opens the Capability Lab locally. It does not expose the monolith to the LAN or internet.

## Truth boundary

One-click usability must not erase evidence boundaries. A capability being visible or launchable does not mean it is verified compatible with every other capability. Candidate connections, failures, uncertainties, and snapshot-bound human/machine evidence remain visible in the interface.
