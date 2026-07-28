# Architecture Blueprint Generator

Use a Blueprint model when the user wants a coordinated set of architecture diagrams rather than one page.

```bash
python3 <skill-dir>/scripts/drawio_tool.py blueprint architecture.blueprint.json \
  -o architecture-blueprint.drawio \
  --ir-output architecture-blueprint.diagram.json \
  --preview-dir architecture-previews \
  --strict
```

## Model

Define:

- `blueprint`: title, direction, and theme.
- `elements`: actors, external systems, systems, containers, components, data resources, and infrastructure.
- `relations`: directed dependencies, calls, events, and data flows.
- `decisions`: optional architecture decisions with status, rationale, and affected element IDs.
- `views`: optional subset of `context`, `logical`, `data`, `deployment`, `security`, and `decisions`.

Use `parent` to express System → Container → Component hierarchy. Use `domain` for logical grouping, `zone` for network/security grouping, and `deploy_to` to map applications onto infrastructure. A deployment target must have `scope: infrastructure`.

Validate authoring tools against [blueprint.schema.json](blueprint.schema.json). Start from [example.blueprint.json](../assets/example.blueprint.json).

## Automatic views

- **Context**: actors, external systems, and systems. Relations from descendants collapse to the nearest visible ancestor. System nodes link to the logical page.
- **Logical**: non-infrastructure elements grouped by domain. Parent system shells with visible children are omitted to reduce duplication.
- **Data**: data resources and directly connected producers/consumers, grouped by domain.
- **Deployment**: deployable elements and infrastructure, grouped by zone and laid out top-to-bottom. `deploy_to` becomes a `hosts` relation.
- **Security**: non-infrastructure elements grouped by security zone, with cross-zone relations retained.
- **Decisions**: decision notes connected to affected architecture elements. Non-infrastructure elements link back to the logical page.

The generator skips optional views that have no qualifying elements and removes links to omitted pages. Use `--views context,logical,deployment` to request a smaller pack.

## Authoring rules

- Model facts only. Do not invent zones, deployment targets, technologies, or relations.
- Give every element and relation a stable kebab-case ID.
- Keep `scope` semantic and `kind` visual: a data element may use `kind: queue` or `kind: database`.
- Put concise technical context in `technology` or `runtime`; keep labels presentation-friendly.
- Split blueprints above roughly 30 logical elements by bounded context.
- Inspect every generated SVG page. A structurally valid pack can still communicate the wrong hierarchy.
