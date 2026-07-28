---
name: drawio-diagram-engineer
description: Create, edit, import, compile, inspect, audit, preview, and export editable draw.io diagrams from natural-language requirements, structured JSON/YAML, Python or TypeScript source trees, OpenAPI, SQL DDL, or Docker Compose. Generate coordinated architecture blueprints, field-level Crow's Foot ERDs, and high-availability topology/failover packs with failure domains, replication, health checks, RTO, and RPO. Apply reusable organization themes, verified shapes, contrast checks, and structured repairs. Use for architecture diagrams, database schemas, HA/DR designs, codebase maps, flowcharts, data flows, UML-style diagrams, network maps, multi-page system views, and repairing or quality-checking existing .drawio files. Prefer when output must remain editable, deterministic, reviewable in source control, or exportable to PNG, SVG, or PDF.
---

# Draw.io Diagram Engineer

Build diagrams through a small, deterministic intermediate representation (IR). Treat the IR as the source of truth and `.drawio` as the compiled artifact.

## Workflow

1. Inspect the request and relevant source material. Infer a sensible diagram type, scope, direction, and theme when the user does not specify them.
   For a coordinated architecture diagram pack, read [blueprint.md](references/blueprint.md), author against [blueprint.schema.json](references/blueprint.schema.json), and use `blueprint`.
   For an ERD, read [erd.md](references/erd.md), author against [erd.schema.json](references/erd.schema.json), and use `erd`. Accept SQL DDL directly when it is the source of truth.
   For high availability, read [ha.md](references/ha.md), author against [ha.schema.json](references/ha.schema.json), and use `ha`.
2. Write a Diagram IR JSON file. Read [ir-format.md](references/ir-format.md) for the schema and [authoring.md](references/authoring.md) for diagram-specific choices. Use [diagram-ir.schema.json](references/diagram-ir.schema.json) with schema-aware tooling.
   When starting from a Python/TypeScript tree, OpenAPI, SQL, or Compose, read [importers.md](references/importers.md) and generate the IR with `import`.
   When organization styling or deeper visual QA is required, read [style-system.md](references/style-system.md) and use a validated theme pack.
3. Compile it:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py compile diagram.json -o diagram.drawio
   ```

4. Run the deterministic quality gate:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py validate diagram.drawio --strict
   ```

5. Create a dependency-free SVG preview:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py preview diagram.json -o diagram.preview.svg
   ```

6. For a structured repair report, audit the source and generated geometry:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py audit diagram.json \
     -o diagram.audit.json --preview-dir diagram.audit-previews --strict
   ```

7. If draw.io Desktop is available, render the authoritative preview:

   ```bash
   python3 <skill-dir>/scripts/drawio_tool.py render diagram.drawio -o diagram.png
   ```

8. Inspect the preview visually. Fix hierarchy, clipped text, collisions, unclear edges, weak contrast, and excess detail. Repeat compile, validate, and preview at most twice before presenting the best result.
9. Deliver the editable `.drawio`, the IR source, audit report, and requested exports. State clearly when Desktop export was skipped.

## Editing existing diagrams

Preserve the user's artifact. Start by inspecting and validating it:

```bash
python3 <skill-dir>/scripts/drawio_tool.py inspect existing.drawio
python3 <skill-dir>/scripts/drawio_tool.py validate existing.drawio
```

For an IR-backed diagram, write semantic operations and apply them atomically:

```bash
python3 <skill-dir>/scripts/drawio_tool.py patch diagram.json changes.json -o diagram.updated.json
```

Read [patching.md](references/patching.md) before destructive or multi-page edits. For an XML-only diagram, modify matching `mxCell` values, styles, or geometry without regenerating unrelated cells. Never renumber stable IDs merely for tidiness.

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

- `compile`: validate IR, calculate deterministic layout, and emit uncompressed editable draw.io XML.
- `blueprint`: project one architecture model into context, logical, data, deployment, security, and decision pages.
- `erd`: validate entities, fields, keys, types, and cardinalities, then generate an editable Crow's Foot ERD from a model or SQL DDL.
- `ha`: validate failure domains, replicas, replication, health checks, and failovers, then generate topology and failover pages.
- `import`: convert Python/TypeScript module trees, OpenAPI, SQL DDL, or Docker Compose into Diagram IR.
- `patch`: atomically apply semantic node, edge, group, position, and diagram changes.
- `preview`: create a reviewable SVG without draw.io Desktop.
- `audit`: inspect structured source and generated geometry, then group findings with repair suggestions and preview paths.
- `validate`: lint IR or `.drawio`, print a 0–100 quality score, and fail under `--strict`.
- `inspect`: summarize pages, nodes, edges, groups, and canvas bounds.
- `render`: discover the draw.io Desktop CLI and export PNG, SVG, PDF, or JPG.

Before first use, verify `python3 -c "import xml.etree.ElementTree"`. If a macOS Homebrew Python reports a `pyexpat`/`libexpat` symbol error, use `/usr/bin/python3` or repair that Python installation; do not attribute the ABI failure to the diagram input.

Use [example.architecture.json](assets/example.architecture.json), [example.blueprint.json](assets/example.blueprint.json), [example.erd.json](assets/example.erd.json), or [example.ha.json](assets/example.ha.json) as a compact starting point, not as a fixed template. Apply [corporate.json](assets/themes/corporate.json) when a reusable custom theme example is useful.
