# Style system and visual audit

Use a theme pack when diagrams must follow an organization-wide palette. A pack has a stable kebab-case name and complete tokens for canvas, groups, edges, and every semantic node kind.

```bash
python3 <skill-dir>/scripts/drawio_tool.py compile diagram.json \
  -o diagram.drawio \
  --theme-file <skill-dir>/assets/themes/corporate.json
```

Author packs against [theme-pack.schema.json](theme-pack.schema.json). The built-in [corporate.json](../assets/themes/corporate.json) is a reusable example. Theme text/fill combinations are checked against a 4.5:1 contrast target.

## Shape registry

[shape-registry.json](../assets/shape-registry.json) maps semantic kinds to a conservative allowlist of core mxGraph and draw.io Shapes.js identifiers. Every entry includes source and license provenance. Extend the registry only after verifying the exact shape identifier in an official JGraph source.

Do not copy third-party proprietary stencil definitions into the project. Use a neutral rectangle until a shape can be verified and licensed.

## Structured audit

Run a complete source, generated-XML, and visual-review audit:

```bash
python3 <skill-dir>/scripts/drawio_tool.py audit diagram.json \
  -o audit.json \
  --preview-dir audit-previews \
  --strict
```

The input may be Diagram IR, an Architecture Blueprint model, or an existing `.drawio` file. For structured inputs, the audit compiles a temporary editable diagram and checks the resulting geometry. The report contains:

- the 0–100 score and structural summary;
- contrast, text-density, clipping, overlap, and routing findings;
- repair suggestions grouped by finding code and target;
- generated SVG preview paths and a manual review checklist.

`audit --strict` fails on errors or a score below 90. A high score does not replace visual review; it establishes a reproducible baseline.
