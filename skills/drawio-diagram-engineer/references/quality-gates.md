# Quality gates

The validator starts at 100 and deducts points for deterministic defects.

## Blocking errors

- malformed JSON, YAML, or XML
- duplicate IDs
- missing edge endpoints
- self-loops in IR
- invalid parent references
- overlapping non-container vertices

`--strict` exits non-zero for any error or a score below 90.

## Warnings

- labels likely to be clipped
- negative coordinates
- very large canvas bounds
- unknown fields or kinds
- isolated nodes
- text density above 5.5 characters per 1000 px²
- text/fill contrast below 4.5:1
- potential connector crossings and node-route intersections

Run `audit` to group these findings by code, attach source-level repair suggestions, and generate an SVG visual-review manifest. See [style-system.md](style-system.md).

## Visual review

Static geometry cannot fully evaluate:

- edge crossings or visual tangles
- semantic hierarchy
- color perception under every display condition
- whether labels are concise and meaningful
- whether the diagram tells the intended story

Render a PNG and inspect it after deterministic validation. Prefer targeted IR changes over ad hoc XML edits so the result stays reproducible.
