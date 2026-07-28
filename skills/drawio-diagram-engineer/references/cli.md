# CLI reference

Read this reference when composing commands, automating the tool, or interpreting exit codes. All paths are local. Commands print JSON except `doctor` in its default human format and fatal errors on stderr.

## Guided workflow

```text
doctor [--format human|json]
init <profile> [-o <starter>] [--force]
build <model|source> [-o <bundle-dir>] [--type <type>] [--name <name>]
      [--title <title>] [--theme-file <theme.json>] [--max-files 500]
      [--strict] [--force]
```

`init` profiles: `architecture`, `blueprint`, `erd`, `ha`, `routing`, `terraform`, `kubernetes`, `github-actions`, and `gitlab-ci`.

`build` types: `auto`, `diagram`, `blueprint`, `erd`, `sql-erd`, `ha`, `python`, `typescript`, `openapi`, `sql`, `compose`, `terraform`, `kubernetes`, `github-actions`, and `gitlab-ci`.

## Contract and security

```text
migrate <legacy-ir> [-o <v1-ir>] [--report <report.json>] [--check]
security <model|diagram.drawio|bundle-dir> [-o <report.json>] [--strict]
```

`migrate --check` writes no model. It exits `6` when a deterministic migration is required and `0` when the input already conforms.

`security` lists external web/mail links without fetching them. Errors include suspected credentials, private keys, unsafe schemes, prohibited XML declarations, and size-limit violations.

## Model generation

```text
blueprint <model.json> -o <pack.drawio> [--ir-output <ir.json>]
          [--preview-dir <dir>] [--views <csv>] [--theme-file <theme.json>] [--strict]
erd <model.json|schema.sql> -o <erd.drawio> [--title <title>]
    [--ir-output <ir.json>] [--preview-dir <dir>] [--theme-file <theme.json>] [--strict]
ha <model.json> -o <ha.drawio> [--ir-output <ir.json>]
   [--preview-dir <dir>] [--theme-file <theme.json>] [--strict]
```

## IR and source operations

```text
compile <ir.json> -o <diagram.drawio> [--theme-file <theme.json>]
import <source> -o <ir.json> [--type <type>] [--title <title>] [--max-files 500]
patch <ir.json> <operations.json> -o <updated.json>
diff <baseline.json> <candidate.json> -o <report.json>
     [--diagram-output <drift.drawio>] [--preview-dir <dir>] [--fail-on-drift]
```

Importer types: `auto`, `python`, `typescript`, `openapi`, `sql`, `compose`, `terraform`, `kubernetes`, `github-actions`, and `gitlab-ci`.

## Review and export

```text
preview <ir.json> -o <preview.svg> [--page <id>] [--theme-file <theme.json>]
audit <model|ir|diagram.drawio> [-o <report.json>] [--preview-dir <dir>]
      [--theme-file <theme.json>] [--strict]
validate <model|ir|diagram.drawio> [--strict]
inspect <diagram.drawio>
render <diagram.drawio> -o <output.png|svg|pdf|jpg> [-f <format>]
       [--width 2000] [--embed] [--binary <drawio-executable>]
       [--report <export-report.json>]
verify-export <output.png|svg|pdf|jpg> [-f <format>] [-o <export-report.json>]
```

`render --binary` takes precedence over `DRAWIO_DESKTOP_BINARY`, which takes precedence over platform auto-discovery.
`render` always verifies the generated artifact before succeeding. `verify-export` applies the same checks without launching Desktop. Both emit `drawio-export-report/v1`; see [desktop-export.md](desktop-export.md) and [export-report.schema.json](export-report.schema.json).

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | Invalid input, structural/security error, or failed operation |
| `3` | Strict quality or warning gate failed |
| `4` | draw.io Desktop unavailable |
| `5` | Drift found with `--fail-on-drift` |
| `6` | Migration required with `migrate --check` |
