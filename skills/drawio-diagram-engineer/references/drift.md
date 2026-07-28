# Architecture drift

Compare two valid Diagram IR documents by semantic page, group, node, and edge IDs:

```bash
python3 <skill-dir>/scripts/drawio_tool.py diff \
  baseline.diagram.json candidate.diagram.json \
  -o drift.report.json \
  --diagram-output drift.drawio \
  --preview-dir drift-previews
```

The JSON report follows [drift-report.schema.json](drift-report.schema.json). Added, removed, and changed elements include their page and semantic ID plus before/after values. The optional editable drift diagram uses:

- green solid nodes and edges for additions;
- red dashed nodes and edges for removals;
- amber nodes and edges for semantic changes.

Status text is included in labels or descriptions, so color is not the only signal. Unchanged elements remain as context.

## Semantic comparison

The comparator intentionally ignores node `position`, `size`, and visual `style`, plus edge `style`. Moving a node or changing presentation does not constitute architecture drift. It compares labels, kinds, groups, descriptions, links, entity fields, endpoints, relation labels, and relation kinds.

Page title changes are reported. The current contract does not treat theme, direction, gap, canvas background, or generated draw.io geometry as architecture drift.

## CI gate

Use `--fail-on-drift` when any detected change should fail the job:

```bash
python3 <skill-dir>/scripts/drawio_tool.py diff \
  approved.diagram.json generated.diagram.json \
  -o architecture-drift.json --fail-on-drift
```

Exit code `5` means valid inputs were compared and drift exists. Exit code `2` means the input or command failed validation. A no-drift comparison exits `0`.

Review removals and endpoint changes before additions. A generated report is evidence of structural difference, not proof that the difference is harmful or unauthorized.
