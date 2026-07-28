# Diagram IR format

Use JSON by default. YAML requires PyYAML. The current schema version is `1`.
The machine-readable contract is [diagram-ir.schema.json](diagram-ir.schema.json).

```json
{
  "version": "1",
  "diagram": {
    "title": "Checkout platform",
    "direction": "LR",
    "theme": "light"
  },
  "groups": [
    {"id": "edge", "label": "Edge"},
    {"id": "services", "label": "Services"}
  ],
  "nodes": [
    {
      "id": "web",
      "label": "Web app",
      "kind": "client",
      "group": "edge",
      "description": "Customer storefront"
    },
    {
      "id": "api",
      "label": "API gateway",
      "kind": "service",
      "group": "services"
    }
  ],
  "edges": [
    {
      "id": "web-to-api",
      "from": "web",
      "to": "api",
      "label": "HTTPS",
      "kind": "sync"
    }
  ]
}
```

## Diagram

- `title`: page title.
- `direction`: `LR` or `TB`.
- `theme`: `light`, `dark`, or `colorblind`.
- `theme_tokens`: optional complete organization theme token object. Prefer applying a validated pack with `--theme-file`; see [style-system.md](style-system.md).
- `gap`: optional integer from 40 to 400.
- `background`: optional hex color.

## Multi-page diagrams

Replace top-level `groups`, `nodes`, and `edges` with `pages`. Each page requires `id`, `title`, `nodes`, and `edges`; `groups` and page-level `diagram` overrides are optional.

```json
{
  "version": "1",
  "diagram": {"direction": "LR", "theme": "colorblind"},
  "pages": [
    {
      "id": "context",
      "title": "System context",
      "nodes": [
        {"id": "platform", "label": "Platform", "kind": "service", "link": "containers"}
      ],
      "edges": []
    },
    {
      "id": "containers",
      "title": "Containers",
      "nodes": [{"id": "api", "label": "API", "kind": "service"}],
      "edges": []
    }
  ]
}
```

Cell IDs are page-local. A node `link` points to another page ID and compiles into a clickable draw.io page link.

## Groups

Groups are visual regions. Each requires a unique `id` and a short `label`. Nodes reference a group by ID.

## Nodes

Required fields are `id` and `label`.

- `kind`: `client`, `service`, `database`, `queue`, `external`, `decision`, `process`, `document`, `note`, or `entity`.
- `group`: ID of a declared group.
- `description`: secondary text shown below the label.
- `position`: optional `{ "x": 100, "y": 120 }`.
- `size`: optional `{ "width": 180, "height": 80 }`.
- `style`: optional safe overrides: `fill`, `stroke`, `font`, `dashed`, `rounded`.
- `link`: optional target page ID for multi-page drill-down.
- `fields`: field rows for `entity` nodes. Use the `erd` command instead of writing entity IR directly when possible.

Use lowercase kebab-case IDs. IDs become stable draw.io cell IDs with a `node-` prefix.

## Edges

Required fields are `from` and `to`.

- `id`: optional stable ID. The compiler derives one when omitted.
- `label`: relationship verb or protocol.
- `kind`: `sync`, `async`, `data`, `dependency`, or `association`.
- `style`: optional safe overrides: `color`, `dashed`, `width`.
- `style.start_cardinality` / `style.end_cardinality`: ER endpoint cardinalities emitted by the `erd` command.

Every endpoint must reference a declared node. Self-loops are rejected.

## Compatibility

Unknown top-level and object fields produce warnings so future extensions remain forward-compatible. Invalid required fields are errors. Keep the IR in source control alongside the generated `.drawio`.
