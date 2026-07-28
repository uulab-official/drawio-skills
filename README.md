# drawio-skills

An open-source, deterministic diagram engineering skill for AI coding agents.

`drawio-diagram-engineer` turns a compact Diagram IR into editable `.drawio` XML, validates the result with a measurable quality gate, and exports through draw.io Desktop when available. The project is intentionally compiler-oriented: the structured IR is reviewable source, and `.drawio` is a reproducible build artifact.

> Status: **v0.5 alpha**. Deterministic compilation, six-view architecture blueprint packs, reusable theme tokens, verified shape mappings, structured visual audits, semantic patches, source importers, and dependency-free previews are usable.

![Order-processing architecture generated from Diagram IR](docs/example.architecture.svg)

## Why another draw.io skill?

[Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill) is an excellent broad toolbox and a key inspiration for this project. This repository explores a different center of gravity:

- **IR-first:** natural language and future code/IaC importers target one versioned schema.
- **Deterministic:** semantic IDs and stable layout make diffs and regeneration predictable.
- **Quality-gated:** structural defects and layout collisions produce machine-readable findings and a 0–100 score.
- **Agent-portable:** the core JSON workflow uses only the Python standard library.
- **Safe evolution:** the editable source and generated artifact can be reviewed independently.

This is an independent implementation. No source code from the inspiration repository is included.

## Quick start

```bash
python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  compile skills/drawio-diagram-engineer/assets/example.architecture.json \
  -o order-processing.drawio

python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  validate order-processing.drawio --strict

python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  preview skills/drawio-diagram-engineer/assets/example.architecture.json \
  -o order-processing.preview.svg
```

Desktop-quality PNG/SVG/PDF/JPG export requires [draw.io Desktop](https://github.com/jgraph/drawio-desktop). Import, patch, compile, validate, inspect, and SVG preview do not.

## Architecture blueprint pack

Generate six coordinated architecture pages—System Context, Logical Architecture, Data Flow, Deployment, Network & Security, and Architecture Decisions—from one model:

```bash
python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  blueprint skills/drawio-diagram-engineer/assets/example.blueprint.json \
  -o commerce-blueprint.drawio \
  --ir-output commerce-blueprint.diagram.json \
  --preview-dir commerce-blueprint-previews \
  --strict
```

The model uses hierarchy, bounded domains, deployment mappings, and security zones to project each view without duplicating its source of truth. See the [Blueprint reference](skills/drawio-diagram-engineer/references/blueprint.md).

Preview the generated pages: [Context](docs/blueprint/context.svg), [Logical](docs/blueprint/logical.svg), [Data](docs/blueprint/data.svg), [Deployment](docs/blueprint/deployment.svg), [Network & Security](docs/blueprint/security.svg), and [Architecture Decisions](docs/blueprint/decisions.svg).

The complete example pack is available as an [editable draw.io file](docs/blueprint/commerce-platform.drawio), [generated Diagram IR](docs/blueprint/commerce-platform.diagram.json), and [100-point audit report](docs/blueprint/audit.json).

## Organization themes and visual audit

Apply a reusable theme pack and generate a machine-readable QA report:

```bash
python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  audit skills/drawio-diagram-engineer/assets/example.blueprint.json \
  -o commerce-blueprint.audit.json \
  --preview-dir commerce-blueprint-audit \
  --theme-file skills/drawio-diagram-engineer/assets/themes/corporate.json \
  --strict
```

The audit checks the source plus generated draw.io geometry for contrast, text density, clipping, overlap, and routing risks. It groups findings with targeted repair suggestions and a visual-review checklist. See the [style system reference](skills/drawio-diagram-engineer/references/style-system.md).

## Install as an agent skill

Clone the repository, then copy or symlink `skills/drawio-diagram-engineer` into the skills directory used by your agent:

```bash
git clone https://github.com/uulab-official/drawio-skills.git
ln -s "$PWD/drawio-skills/skills/drawio-diagram-engineer" \
  "$HOME/.codex/skills/drawio-diagram-engineer"
```

The skill follows the Agent Skills folder convention and includes Codex UI metadata in `agents/openai.yaml`.

## Diagram IR

```json
{
  "version": "1",
  "diagram": {"title": "Payments", "direction": "LR", "theme": "colorblind"},
  "groups": [{"id": "platform", "label": "Platform"}],
  "nodes": [
    {"id": "api", "label": "API", "kind": "service", "group": "platform"},
    {"id": "ledger", "label": "Ledger", "kind": "database", "group": "platform"}
  ],
  "edges": [
    {"id": "api-ledger", "from": "api", "to": "ledger", "label": "write", "kind": "data"}
  ]
}
```

See [the IR reference](skills/drawio-diagram-engineer/references/ir-format.md) for supported fields.

## CLI

```text
drawio_tool.py compile <ir.json> -o <diagram.drawio> [--theme-file <theme.json>]
drawio_tool.py blueprint <blueprint.json> -o <pack.drawio> [--ir-output <ir.json>] [--preview-dir <dir>] [--theme-file <theme.json>]
drawio_tool.py import <source-tree|openapi|schema.sql|compose> --type <type> -o <ir.json>
drawio_tool.py patch <ir.json> <operations.json> -o <updated.json>
drawio_tool.py preview <ir.json> -o <preview.svg> [--page <id>] [--theme-file <theme.json>]
drawio_tool.py audit <ir.json|blueprint.json|diagram.drawio> [-o <report.json>] [--preview-dir <dir>] [--strict]
drawio_tool.py validate <ir.json|diagram.drawio> [--strict]
drawio_tool.py inspect <diagram.drawio>
drawio_tool.py render <diagram.drawio> -o <output.png|svg|pdf|jpg> [--embed]
```

JSON works without third-party packages. YAML input is optional and requires PyYAML.

## Roadmap

The next milestone returns to infrastructure intelligence: Terraform, Kubernetes, CI pipelines, diagram diffing, and stronger routing. See the measurable milestone and release criteria in [ROADMAP.md](ROADMAP.md).

## Development

```bash
python3 -m unittest discover -s tests -v
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/drawio-diagram-engineer
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a schema or output compatibility change.

### macOS Python note

If Homebrew Python fails to import `pyexpat` because its `libexpat` symbols do not match, use `/usr/bin/python3` temporarily or reinstall the affected Python/libexpat packages. This is an interpreter ABI problem; JSON-only compilation may appear to work until XML validation starts.

## License

Apache License 2.0. See [LICENSE](LICENSE).
