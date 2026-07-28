# ERD generation

Use `erd` for logical or physical data models that need field-level detail and Crow's Foot cardinality.

```bash
python3 <skill-dir>/scripts/drawio_tool.py erd database.erd.json \
  -o database.drawio \
  --ir-output database.diagram.json \
  --preview-dir database-previews \
  --strict
```

SQL DDL can be used directly:

```bash
python3 <skill-dir>/scripts/drawio_tool.py erd schema.sql \
  -o schema.drawio \
  --title "Application Database" \
  --preview-dir schema-previews \
  --strict
```

Author structured models against [erd.schema.json](erd.schema.json). Start from [example.erd.json](../assets/example.erd.json).

## Model

- `erd`: title, direction, theme, and optional gap.
- `entities`: stable ID, displayed label, optional schema and position, and field definitions.
- `fields`: name, type, nullable, primary-key, foreign-key, unique, and default metadata.
- `relationships`: source and target entities/fields, endpoint cardinalities, identifying flag, and label.

Cardinality values are `one`, `zero-or-one`, `one-or-many`, and `zero-or-many`. The editable draw.io output uses the official `ERmandOne`, `ERzeroToOne`, `ERoneToMany`, and `ERzeroToMany` markers.

## Quality rules

- Give every entity a primary key unless it is intentionally keyless.
- Match foreign-key and referenced-key types.
- Keep `from_fields` and `to_fields` in the same column order for composite keys.
- Use identifying relationships only when the parent key participates in the child primary key.
- Use explicit positions only to resolve a semantic layout problem; deterministic layout remains the default.
- For large schemas, group entities by `schema` and split bounded contexts into separate diagrams.
