# Compatibility and migration

Read this reference before changing a public schema, consuming older Diagram IR, or adding a field that downstream tools may store.

## Public contracts

The following identifiers are independent versioned contracts:

- Diagram IR: `version: "1"` and [diagram-ir.schema.json](diagram-ir.schema.json)
- Bundle manifest: `drawio-diagram-bundle/v1` and [bundle.schema.json](bundle.schema.json)
- Security report: `drawio-security-report/v1`
- Migration report: `drawio-migration-report/v1`
- Export verification report: `drawio-export-report/v1`
- Extraction report: `drawio-extraction-report/v1`
- Review site manifest: `drawio-review-site/v1`
- Review annotations: `version: "1"` and [review-annotations.schema.json](review-annotations.schema.json)

Tool releases use semantic versions. Schema versions do not advance merely because the tool gains a feature.

## Diagram IR v1 guarantees

Within Diagram IR v1:

- Existing required fields, meanings, and accepted values will not be removed or narrowed.
- New optional fields and warnings may be added.
- Unknown fields remain warning-level and must be preserved by migrations and semantic patching.
- Stable semantic IDs continue to determine draw.io cell IDs.
- Given identical IR, theme, tool version, and Python major/minor, compilation remains byte-deterministic.

A breaking schema change requires Diagram IR v2, a documented migration, and at least one final v1-capable release.

Generated `.drawio` XML is an artifact contract, not an API for positional assumptions. Semantic cell IDs and editability are stable; internal style ordering and calculated coordinates may improve between tool releases.

Starting in tool v1.1, generated files include `data-ir-version`, `data-ir-page`, and semantic `data-ir` cell attributes. These attributes are additive draw.io metadata and power [round-trip extraction](round-trip.md). Consumers must preserve unknown `data-*` attributes when modifying compiler-owned XML. Removing them does not make the file unreadable, but `extract --strict` will correctly classify the affected content as inferred rather than lossless.

## Deprecation policy

Deprecations are announced as validator warnings for at least two minor releases before removal in a new major schema version. Each warning must name the replacement and link to a migration path in release notes.

Security-critical behavior may be rejected immediately. Such changes must be documented in the security reference and changelog.

## Legacy migration

Use:

```bash
python3 <skill-dir>/scripts/drawio_tool.py migrate legacy.json \
  -o diagram.json --report migration.json
```

Use `--check` in CI. Exit code `6` means the file is validly migratable but changes are required.

The legacy adapter accepts unversioned or `version: 0` Diagram IR and performs these deterministic transformations:

| Legacy field/value | Diagram IR v1 |
| --- | --- |
| `layout` | `diagram` |
| root `title`, `direction`, `theme`, `gap`, `background` | matching `diagram.*` field |
| `components` | `nodes` |
| `connections` | `edges` |
| node `type` | `kind` |
| node `container` | `group` |
| edge `source` / `target` | `from` / `to` |
| edge `type` | `kind` |
| node kinds `api`, `app`, `broker`, `db`, `user` | `service`, `service`, `queue`, `database`, `client` |
| missing edge ID | deterministic `<from>-to-<to>` ID |

Conflicting old and new fields fail instead of guessing. Unsupported versions fail without modifying the source.

## Bundle evolution

Bundle v1 may gain optional artifacts. Existing artifact paths retain their meaning. Inputs are never copied into a bundle. Consumers must ignore unknown manifest properties and locate files through `artifacts`, not hard-coded directory scans.

Review site v1 may gain optional evidence, catalog, and annotation fields. Existing page artifact and report paths retain their meaning. Consumers should read `review.json` rather than scraping `index.html`.
