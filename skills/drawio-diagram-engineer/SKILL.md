---
name: drawio-diagram-engineer
description: Create, edit, import, extract, compare, compile, migrate, audit, publish, and export editable draw.io diagrams from natural language, JSON/YAML, existing .drawio files, code, OpenAPI, SQL, Compose, Terraform, Kubernetes, GitHub Actions, or GitLab CI. Generate architecture blueprints, field-level Crow's Foot ERDs, HA/failover packs, infrastructure maps, pipelines, semantic drift reports, and portable HTML/SVG review sites with annotations and visual baselines. Apply deterministic layout, round-trip metadata, explicit ports, obstacle-aware routing, themes, contrast, credential checks, and structured repairs. Use for architecture, database schemas, HA/DR, codebase and deployment topology, flowcharts, data flows, network maps, multi-page views, architecture review publication, legacy IR migration, or .drawio repair. Prefer when output must stay editable, deterministic, secure, source-reviewable, CI-gated, shareable without Desktop, or exportable to PNG, SVG, or PDF.
---

# Draw.io Diagram Engineer

Build diagrams through a small, deterministic intermediate representation (IR). Treat the IR as the source of truth and `.drawio` as the compiled artifact.

## Workflow

1. On first use or after an environment failure, run `doctor`. Read [user-workflows.md](references/user-workflows.md) for capability states, starter selection, bundle contents, and safe overwrite behavior. Read [cli.md](references/cli.md) when composing less common commands or interpreting exit codes.
   For legacy or versioned Diagram IR, read [compatibility.md](references/compatibility.md) and run `migrate --check` before editing.
2. Inspect the request and relevant source material. Infer a sensible diagram type, scope, direction, and theme when the user does not specify them.
   For a coordinated architecture diagram pack, read [blueprint.md](references/blueprint.md), author against [blueprint.schema.json](references/blueprint.schema.json), and use `blueprint`.
   For an ERD, read [erd.md](references/erd.md), author against [erd.schema.json](references/erd.schema.json), and use `erd`. Accept SQL DDL directly when it is the source of truth.
   For high availability, read [ha.md](references/ha.md), author against [ha.schema.json](references/ha.schema.json), and use `ha`.
3. Write or adapt the smallest structured source. Use `init architecture`, `init blueprint`, `init erd`, or `init ha` when no source exists. Read [ir-format.md](references/ir-format.md) for Diagram IR and [authoring.md](references/authoring.md) for diagram-specific choices.
   When starting from a Python/TypeScript tree, OpenAPI, SQL, Compose, Terraform, Kubernetes, GitHub Actions, or GitLab CI, read [importers.md](references/importers.md) and generate the IR with `import`.
   When automatic connectors remain visually ambiguous or a fixed interface matters, read [routing.md](references/routing.md) before assigning explicit ports.
   When organization styling or deeper visual QA is required, read [style-system.md](references/style-system.md) and use a validated theme pack.
   When importing untrusted content or preparing a release bundle, read [security.md](references/security.md). Never place credentials in labels, descriptions, links, metadata, or entity defaults.
4. Prefer the one-command bundle workflow:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py build source.json \
     -o build/diagram --name diagram --strict
   ```

   This creates normalized IR, editable `.drawio`, all SVG previews, `audit.json`, `security.json`, and `bundle.json`. Use the lower-level `compile`, `validate`, `preview`, `security`, and `audit` commands only when the user needs individual artifacts or an incremental workflow.
5. When reviewers need one portable artifact or CI needs an architecture evidence index, read [collaborative-review.md](references/collaborative-review.md) and publish the bundle:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py publish build/diagram \
     -o build/diagram-review --strict
   ```

6. If draw.io Desktop is available and a Desktop export is requested, read [desktop-export.md](references/desktop-export.md), render from the bundle's `.drawio`, and retain its verification report:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py render build/diagram/diagram.drawio \
     -o diagram.png --report diagram.export.json
   ```

7. Inspect every bundled or published preview visually. Fix hierarchy, clipped text, collisions, unclear edges, weak contrast, and excess detail. Rebuild at most twice before presenting the best result.
8. Deliver the bundle's editable `.drawio`, IR source, audit report, previews, review site, and requested exports. State clearly when Desktop export was skipped.

When comparing an approved architecture with a newly generated model, read [drift.md](references/drift.md), run `diff`, and deliver both the machine-readable report and editable drift view.

## Editing existing diagrams

Preserve the user's artifact. Start by inspecting and validating it:

```bash
python3 <skill-dir>/scripts/drawio_tool.py inspect existing.drawio
python3 <skill-dir>/scripts/drawio_tool.py validate existing.drawio
```

Recover reviewable Diagram IR before semantic edits:

```bash
python3 <skill-dir>/scripts/drawio_tool.py extract existing.drawio \
  -o existing.diagram.json --report existing.extraction.json --strict
```

Read [round-trip.md](references/round-trip.md) before relying on a recovered model. `lossless: true` means all semantic cells used supported compiler metadata. A valid best-effort model may still be written when `--strict` exits `3`; review every inferred cell before replacing the original.

For an IR-backed diagram, write semantic operations and apply them atomically:

```bash
python3 <skill-dir>/scripts/drawio_tool.py patch diagram.json changes.json -o diagram.updated.json
```

Read [patching.md](references/patching.md) before destructive or multi-page edits. If extraction reports unsupported XML-only content, modify only matching `mxCell` values, styles, or geometry and preserve the original until visual review passes. Never renumber stable IDs merely for tidiness.

## Quality contract

Require all of the following before delivery:

- No dangling edge endpoints, duplicate IDs, invalid parent references, or node overlaps.
- Labels fit their nodes and remain readable at normal zoom.
- Direction and grouping communicate the intended hierarchy.
- Edge labels describe relationships, not implementation trivia.
- Color carries a consistent meaning and does not become the only differentiator.
- Decorative detail does not overwhelm the primary reading path.

Use `--strict` as a release gate. Read [quality-gates.md](references/quality-gates.md) when a check fails or a diagram needs manual visual review.

## Authoring rules

- Use stable, semantic IDs such as `api-gateway`, not ordinal IDs such as `node-7`.
- Keep labels short. Put longer context in `description`.
- Use explicit `group` values for tiers, trust zones, bounded contexts, or ownership.
- Prefer left-to-right for request/data pipelines and top-to-bottom for processes or hierarchies.
- Keep one primary idea per diagram. Split large systems into multiple pages or levels rather than shrinking everything.
- Use `position` only when the user needs intentional placement; otherwise let the compiler lay out nodes deterministically.
- Do not guess vendor-specific draw.io stencil names. Use a neutral semantic kind until a verified shape mapping exists.

## Tool behavior

`scripts/drawio_tool.py` is standard-library-only for JSON input. YAML input is supported when PyYAML is installed. It provides:

- `doctor`: verify core files and Python/XML support, then report optional YAML and Desktop capabilities.
- `init`: copy a safe starter for architecture, Blueprint, ERD, HA, routing, infrastructure, or CI.
- `build`: auto-detect a model or source and create a complete, audited `drawio-diagram-bundle/v1`.
- `publish`: create an atomic script-free `drawio-review-site/v1` with page navigation, semantic anchors, annotations, evidence status, and optional visual-baseline gating.
- `migrate`: deterministically upgrade legacy/unversioned Diagram IR and emit a machine-readable change report.
- `compile`: validate IR, calculate deterministic layout, and emit uncompressed editable draw.io XML.
- `extract`: recover Diagram IR from compressed or uncompressed draw.io, preserving compiler-backed semantics and reporting every inferred legacy cell.
- `blueprint`: project one architecture model into context, logical, data, deployment, security, and decision pages.
- `erd`: validate entities, fields, keys, types, and cardinalities, then generate an editable Crow's Foot ERD from a model or SQL DDL.
- `ha`: validate failure domains, replicas, replication, health checks, and failovers, then generate topology and failover pages.
- `import`: convert Python/TypeScript module trees, OpenAPI, SQL DDL, Docker Compose, Terraform, Kubernetes, GitHub Actions, or GitLab CI into Diagram IR.
- `diff`: compare Diagram IR semantically, emit a structured drift report, and optionally generate an editable color-and-shape-coded drift view.
- `patch`: atomically apply semantic node, edge, group, position, and diagram changes.
- `preview`: create a reviewable SVG without draw.io Desktop.
- `audit`: inspect structured source and generated geometry, then group findings with repair suggestions and preview paths.
- `security`: scan a model, `.drawio`, or complete bundle for credentials, unsafe links, prohibited XML constructs, and decompression risks.
- `validate`: lint IR or `.drawio`, print a 0–100 quality score, and fail under `--strict`.
- `inspect`: summarize pages, nodes, edges, groups, and canvas bounds.
- `render`: discover the draw.io Desktop CLI across macOS, Windows, and Linux, honor `DRAWIO_DESKTOP_BINARY` or `--binary`, and export PNG, SVG, PDF, or JPG.
- `verify-export`: validate the format signature, structural terminator, dimensions, and safe SVG content of a native export without launching Desktop.

Before first use, verify `python3 -c "import xml.etree.ElementTree"`. If a macOS Homebrew Python reports a `pyexpat`/`libexpat` symbol error, use `/usr/bin/python3` or repair that Python installation; do not attribute the ABI failure to the diagram input.

Use [example.architecture.json](assets/example.architecture.json), [example.blueprint.json](assets/example.blueprint.json), [example.erd.json](assets/example.erd.json), [example.ha.json](assets/example.ha.json), [example.routing.json](assets/example.routing.json), [example.terraform.tf](assets/example.terraform.tf), or [example.kubernetes.json](assets/example.kubernetes.json) as a compact starting point, not as a fixed template. Apply [corporate.json](assets/themes/corporate.json) when a reusable custom theme example is useful.
