# User workflows

Use this reference when onboarding a user, choosing a starter, creating a complete bundle, or explaining a command failure.

## Choose the shortest path

| Starting point | Command or profile | Result |
| --- | --- | --- |
| New system overview | `init architecture` | One-page editable architecture |
| Architecture definition document | `init blueprint` | Context, logical, data, deployment, security, and decision pages |
| Database design | `init erd` | Field-level Crow's Foot ERD |
| Existing SQL DDL | `build schema.sql` | SQL-derived Crow's Foot ERD |
| Resilience design | `init ha` | HA topology and failover pages |
| Terraform or source repository | `build <directory>` | Auto-detected topology or dependency map |
| Kubernetes/OpenAPI/Compose/CI file | `build <file>` | Auto-detected editable topology |
| Existing Diagram IR | `build diagram.json` | Complete delivery bundle |

## First-use check

Run:

```bash
python3 <skill-dir>/scripts/drawio_tool.py doctor
```

`FAIL` prevents core generation. `OPTIONAL` only disables the named capability. Missing PyYAML does not affect JSON, and missing draw.io Desktop does not affect editable `.drawio` or dependency-free SVG generation.

## Create and build

Create a starter:

```bash
python3 <skill-dir>/scripts/drawio_tool.py init blueprint -o architecture.json
```

Edit its semantic IDs, labels, components, and relationships, then produce the whole deliverable:

```bash
python3 <skill-dir>/scripts/drawio_tool.py build architecture.json \
  -o build/architecture --strict
```

The output directory contains:

- `diagram.json`: normalized Diagram IR, suitable for review and regeneration.
- `<name>.drawio`: editable, uncompressed draw.io XML.
- `previews/*.svg`: one dependency-free review preview per page.
- `audit.json`: the 0–100 quality score, findings, and suggested repairs.
- `bundle.json`: a stable `drawio-diagram-bundle/v1` artifact manifest.

The input is referenced by name but is not copied into the bundle.

## Detection and overrides

`build --type auto` is the default. It recognizes structured Blueprint, ERD, HA, and Diagram IR models before source import. A `.sql` file defaults to the richer field-level ERD path.

When a generic file or mixed repository is ambiguous, pass one of:

```text
--type diagram
--type blueprint
--type erd
--type sql-erd
--type ha
--type python
--type typescript
--type openapi
--type sql
--type compose
--type terraform
--type kubernetes
--type github-actions
--type gitlab-ci
```

Use generic `--type sql` only for a table dependency overview. Use `--type sql-erd` for fields, keys, types, and Crow's Foot cardinalities.

## Safe overwrite behavior

`init` refuses to overwrite an existing starter unless `--force` is explicit.

`build` refuses to replace a non-empty output directory. With `--force`, it only replaces a directory whose `bundle.json` identifies it as a `drawio-diagram-engineer` bundle. It will not replace an arbitrary directory.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Completed; the core workflow or quality gate passed |
| `2` | Invalid input, missing required capability, or structural error |
| `3` | `--strict` quality score is below 90 |
| `4` | draw.io Desktop was not found for `render` |
| `5` | Semantic drift found with `diff --fail-on-drift` |

## Troubleshooting

- Run `doctor --format json` when another agent or script needs machine-readable capability state.
- If YAML fails, use JSON or install PyYAML. No third-party package is required for JSON.
- If Desktop export is unavailable, deliver the editable `.drawio` and bundled SVG previews.
- If automatic source detection fails, pass `--type` explicitly.
- If strict mode exits `3`, open `audit.json`, apply the listed repairs at the source-model level, and rebuild.
- On macOS, a `pyexpat` symbol error indicates a broken Python/libexpat pairing. Use `/usr/bin/python3` or repair that interpreter.
