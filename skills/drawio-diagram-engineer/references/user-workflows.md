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
| Existing bundle for review | `publish <bundle>` | Portable HTML/SVG review site |

## First-use check

Run:

```bash
python3 <skill-dir>/scripts/drawio_tool.py doctor
```

`FAIL` prevents core generation. `OPTIONAL` only disables the named capability. Missing PyYAML does not affect JSON, and missing draw.io Desktop does not affect editable `.drawio` or dependency-free SVG generation.

When native PNG/SVG/PDF/JPEG output matters, read [desktop-export.md](desktop-export.md), run `render --report <report.json>`, and retain the verification report with the export.

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
- `security.json`: credential, unsafe-link, and XML safety findings.
- `bundle.json`: a stable `drawio-diagram-bundle/v1` artifact manifest.

The input is referenced by name but is not copied into the bundle.

When the deliverable needs to be reviewed without draw.io Desktop, publish the bundle:

```bash
python3 <skill-dir>/scripts/drawio_tool.py publish build/architecture \
  -o build/architecture-review \
  --policy organization-policy.json \
  --policy team-policy.json \
  --ownership review-ownership.json \
  --fail-on-policy --fail-on-unowned-findings --strict
```

The review site provides page navigation, semantic node/edge/group anchors, persistent reviewer decisions, composed policy status, auditable exceptions, owner-routed SARIF, source provenance, `reports/summary.md`, machine-readable `review.json`, and optional visual-baseline comparison. Use `--carry-review <prior-review>` with an annotation update file to retain accepted and resolved decisions. Read [collaborative-review.md](collaborative-review.md) for the complete contract.

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

`publish` follows the same rule and only replaces a directory with an owned `drawio-review-site/v1` `review.json`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Completed; the core workflow or quality gate passed |
| `2` | Invalid input, missing required capability, or structural error |
| `3` | `--strict` quality score is below 90 |
| `4` | draw.io Desktop was not found for `render` |
| `5` | Semantic drift found with `diff --fail-on-drift` |
| `6` | Diagram IR migration required with `migrate --check` |
| `7` | Published SVG pages differ from the configured visual baseline |
| `8` | An error-level architecture policy or expired exception failed |
| `9` | An explicit ownership gate found one or more unassigned findings |

## Troubleshooting

- Run `doctor --format json` when another agent or script needs machine-readable capability state.
- Run `migrate --check` before editing unversioned or legacy Diagram IR.
- Run `security <bundle> --strict` as the final publication gate.
- Run `publish <bundle> -o <review> --strict` to create a portable evidence index.
- Repeat `--policy <policy.json>` for reusable organization/team layers, use an explicit `--evaluation-date` in reproducible CI, and retain `reports/policy.json`.
- Add `--ownership <ownership.json> --fail-on-unowned-findings` to route SARIF and enforce accountable review coverage.
- Append `reports/summary.md` to the CI job summary; set `--public-base-url` when direct hosted evidence links are available.
- Run `verify-export <artifact>` when checking a native export produced on another machine.
- If YAML fails, use JSON or install PyYAML. No third-party package is required for JSON.
- If Desktop export is unavailable, deliver the editable `.drawio` and bundled SVG previews.
- If automatic source detection fails, pass `--type` explicitly.
- If strict mode exits `3`, open `audit.json`, apply the listed repairs at the source-model level, and rebuild.
- On macOS, a `pyexpat` symbol error indicates a broken Python/libexpat pairing. Use `/usr/bin/python3` or repair that interpreter.
