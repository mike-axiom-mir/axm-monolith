# AXM Monolith Boundary

This file defines what The Assembly may include and what assembly means.

## 1. Public-source boundary

The default assembly source is the current set of eligible **public** repositories owned by the configured AXM GitHub account.

Private repositories are categorically out of scope for automatic discovery and assembly.

This is intentional. Visibility is being used as a hard identity boundary so a machine with broader credentials cannot silently mix private identities, experiments, holders, or unrelated work into a public-stack monolith.

## 2. Explicit opt-out boundary

Public does not mean automatically absorbable forever.

Any repository may be placed in `excluded_repositories` with a reason. The assembler must preserve that exclusion until the configuration itself is deliberately changed.

Current protected exclusion:

- `mike-axiom-mir/axm-collaboration-platform`

The collaboration platform is expected to remain separately bounded. Future interoperability should occur through an explicit protocol/interface, not by importing its internals into the monolith.

## 3. Source repositories remain authoritative for themselves

The Assembly is a derived integration surface.

It may capture, test, index, compare, and compose source modules, but it does not silently become the canonical development location for those modules.

Repairs discovered in an assembled stack should normally be proposed back to the owning source repository with evidence.

## 4. Assembly is not compatibility

A module appearing in the same generated directory as another module proves only co-location at pinned revisions.

It does not prove:

- API compatibility;
- state compatibility;
- semantic equivalence;
- merge safety;
- runtime interoperability;
- correctness of cross-module assumptions.

Those claims require their own evidence.

## 5. Preserve identity by namespace

Every source repository receives one module directory.

```text
modules/<source-repository-name>/
```

No generic file such as `state.json`, `README.md`, `config.json`, `index.html`, or `main.py` from one source may overwrite a same-named file from another source during assembly.

Cross-module links must be explicit.

## 6. Reproducibility before convenience

A build resolves exact commit SHAs before materializing source.

The generated `axm-stack.lock.json` is the point-in-time source truth for that assembly. A future rebuild using the same SHAs should be able to reconstruct the same source set even if default branches have advanced.

## 7. No automatic build

The repository contains no scheduled workflow that silently captures mains.

A full stack snapshot is created only after an explicit build command with explicit confirmation.

This is especially important before the first experiment: the current growth work should be merged first, then the desired moment should be captured deliberately.

## 8. Root boundary

The Assembly follows AXM's roots:

- Truth
- Agency / non-domination
- Continuity
- Wisdom before speed

Its job is to expose what the stack actually is, including collisions, failures, duplication, incompatibilities, and unknowns — not to manufacture a cleaner story than the evidence supports.
