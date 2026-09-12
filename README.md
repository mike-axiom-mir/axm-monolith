# AXM Monolith — The Assembly

**Nickname: The Assembly**

AXM Monolith is the on-demand integration surface for the public AXM stack.

Its job is **not** to become another development home and it is **not** allowed to silently fork or flatten the source repositories. Its job is to answer a narrower question:

> **At this exact moment, what does the current public AXM stack become when we assemble it together without erasing the identity of its parts?**

## Current status

**Assembler foundation only. No monolith snapshot has been created yet.**

The first real assembly is intentionally deferred until the current growth work has been reviewed/merged. Do not commit an assembled stack, generated lock file, or captured main-state snapshot to this repository merely because the assembler exists.

## Source boundary

The default source set is intentionally simple and hard to misread:

- GitHub owner: `mike-axiom-mir`
- **PUBLIC repositories only**
- private repositories are rejected even if credentials can see them
- forks are excluded by default
- archived repositories are excluded by default
- explicit exclusions are applied from `config/assembly.json`
- this repository excludes itself to prevent recursion

The collaboration platform is explicitly excluded:

- `mike-axiom-mir/axm-collaboration-platform`

That exclusion is architectural, not accidental. The collaboration platform may later be called across its own protocol boundary, but it must not be directly absorbed into the stack.

Keeping discovery public-only also provides a clean identity boundary: private repositories are not silently mixed into a monolith because the local machine or token happens to have access to them.

## On-demand model

The Assembly has three modes:

```text
discover   -> read-only list of eligible and rejected repositories
plan       -> read-only exact default-branch SHA plan printed to stdout
build      -> explicit materialization of the full public stack into a new output directory
```

Nothing runs automatically.

A real build requires the explicit `--confirm-build` flag.

## What a build will do later

When explicitly invoked, the assembler will:

1. query the configured owner's public repositories;
2. reject anything outside the public/owner boundary;
3. apply explicit exclusions;
4. resolve the exact current default-branch commit SHA of every eligible repository;
5. pin those SHAs into `axm-stack.lock.json` inside the generated output;
6. materialize each repository at that exact SHA;
7. keep every source repo in its own namespace under `modules/<repo>`;
8. write source/provenance metadata into each module;
9. produce a top-level manifest and inventory;
10. leave every source repository untouched.

The output is therefore a reproducible **point-in-time assembly**, not a claim that all components are mutually compatible or that every composition works.

## Why namespacing matters

The monolith must be whole without becoming identity soup.

```text
monolith/
  axm-stack.lock.json
  MONOLITH_MANIFEST.json
  INVENTORY.md
  modules/
    axm-state-research/
    axm-institution-fabric/
    axm-directional-state-fabric/
    ...
```

Files from different repositories are never flattened into one directory simply because they share a filename or concept. Integration adapters can be built later from evidence.

## Commands

Read-only discovery:

```bash
python tools/assemble.py discover
```

Read-only exact-head plan:

```bash
python tools/assemble.py plan
```

Future explicit build example:

```bash
python tools/assemble.py build \
  --output ../axm-monolith-builds/2026-12-31-test \
  --confirm-build
```

**Do not run the build yet for the first stack test.** The current growth merge batch comes first.

## Truth boundary

A successful assembly means only:

- the selected public repositories were resolved;
- exact SHAs were captured;
- their contents were materialized under preserved namespaces;
- provenance is reproducible.

It does **not** mean:

- the whole stack works together;
- duplicated concepts are equivalent;
- incompatible state models have been reconciled;
- an untested composition is safe;
- a module's claims become stronger because it is inside the monolith.

Those are the experiments The Assembly exists to make easier.

## Start here

Future builders should read:

1. [`START_HERE.md`](START_HERE.md)
2. [`MONOLITH_BOUNDARY.md`](MONOLITH_BOUNDARY.md)
3. [`config/assembly.json`](config/assembly.json)
4. [`tools/assemble.py`](tools/assemble.py)
5. [`NEXT_BUILD.md`](NEXT_BUILD.md)

The first goal is not “make everything compatible.” The first goal is **make the whole eligible public stack reproducibly inspectable at one moment without silently changing what any source repository is.**
