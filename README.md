# drawio-skills

An open-source, deterministic diagram engineering skill for AI coding agents.

`drawio-diagram-engineer` turns a compact Diagram IR into editable `.drawio` XML, validates the result with a measurable quality gate, and exports through draw.io Desktop when available. The project is intentionally compiler-oriented: the structured IR is reviewable source, and `.drawio` is a reproducible build artifact.

> Status: **v0.8 alpha**. Deterministic compilation, explicit ports and obstacle-aware orthogonal routing, architecture blueprint packs, field-level Crow's Foot ERDs, HA topology/failover packs, Terraform/Kubernetes and CI pipeline importers, semantic architecture drift, reusable themes, structured visual audits, and dependency-free previews are usable.

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

## Crow's Foot ERD

Generate a field-level ERD from the structured model or directly from SQL DDL:

```bash
python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  erd skills/drawio-diagram-engineer/assets/example.erd.json \
  -o commerce-erd.drawio \
  --ir-output commerce-erd.diagram.json \
  --preview-dir commerce-erd-previews \
  --strict
```

The ERD profile validates primary and foreign keys, composite-key field order, data-type compatibility, nullable/unique flags, and endpoint cardinalities. The editable output uses official draw.io Crow's Foot markers. See the [ERD reference](skills/drawio-diagram-engineer/references/erd.md).

Open the [editable ERD](docs/erd/commerce-erd.drawio), [generated IR](docs/erd/commerce-erd.diagram.json), [SVG preview](docs/erd/main.svg), or [100-point audit](docs/erd/audit.json).

![Commerce database ERD](docs/erd/main.svg)

## High-availability architecture

Generate separate HA topology and failover views:

```bash
python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  ha skills/drawio-diagram-engineer/assets/example.ha.json \
  -o checkout-ha.drawio \
  --ir-output checkout-ha.diagram.json \
  --preview-dir checkout-ha-previews \
  --strict
```

The HA profile validates independent failure domains, replica counts, quorum shape, stateful replication, automatic-failover health checks, cross-domain promotion, RTO, and RPO. See the [HA reference](skills/drawio-diagram-engineer/references/ha.md).

Open the [editable HA pack](docs/ha/checkout-ha.drawio), [generated IR](docs/ha/checkout-ha.diagram.json), [topology](docs/ha/topology.svg), [failover flow](docs/ha/failover.svg), or [100-point audit](docs/ha/audit.json).

![Checkout high-availability topology](docs/ha/topology.svg)

## Infrastructure and pipeline intelligence

Generate editable topology directly from Terraform, Kubernetes, GitHub Actions, or GitLab CI:

```bash
python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  import ./infra --type terraform -o terraform.diagram.json

python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  import ./manifests --type kubernetes -o kubernetes.diagram.json

python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  import . --type github-actions -o delivery.diagram.json
```

Terraform references become dependency edges. Kubernetes namespaces become groups, with Ingress → Service → workload and workload → configuration/storage relations derived from declared selectors and references. Secret values are redacted. CI jobs are grouped by workflow or stage and ordered from prerequisite to dependent job.

See the complete [importer contract](skills/drawio-diagram-engineer/references/importers.md), the 20-case [infrastructure/CI corpus](tests/fixtures/importers/corpus.json), and the 25-case [legacy importer corpus](tests/fixtures/importers/legacy-corpus.json). Every importer now has at least five deterministic strict-valid fixtures.

Open the editable and audited examples:

- [Terraform diagram](docs/infrastructure/terraform/infrastructure.drawio), [SVG](docs/infrastructure/terraform/main.svg), and [100-point audit](docs/infrastructure/terraform/audit.json).
- [Kubernetes diagram](docs/infrastructure/kubernetes/runtime.drawio), [SVG](docs/infrastructure/kubernetes/main.svg), and [100-point audit](docs/infrastructure/kubernetes/audit.json).
- [GitHub Actions](docs/pipelines/github-actions/pipeline.drawio) and [GitLab CI](docs/pipelines/gitlab-ci/pipeline.drawio), each with a generated SVG and 100-point audit.

![Kubernetes runtime topology imported from manifests](docs/infrastructure/kubernetes/main.svg)

## Semantic architecture drift

Compare two Diagram IR versions while ignoring layout-only movement:

```bash
python3 skills/drawio-diagram-engineer/scripts/drawio_tool.py \
  diff approved.diagram.json generated.diagram.json \
  -o drift.report.json \
  --diagram-output drift.drawio \
  --preview-dir drift-previews \
  --fail-on-drift
```

The report classifies page, group, node, and edge changes by stable semantic ID. The editable view uses green for additions, red dashed shapes for removals, and amber for changes, with text status markers for non-color-only review. See the [drift contract](skills/drawio-diagram-engineer/references/drift.md), [example report](docs/drift/report.json), [editable view](docs/drift/architecture-drift.drawio), [SVG preview](docs/drift/main.svg), and [100-point audit](docs/drift/audit.json).

![Semantic architecture drift view](docs/drift/main.svg)

## Deterministic ports and routing

Automatic edges select the side facing their target, distribute fan-out/fan-in attachment points, and choose an orthogonal corridor by node intersections, unrelated edge crossings, bend count, and length. Assign a fixed interface only when the topology requires it:

```json
{
  "id": "monitor-api",
  "from": "monitor",
  "to": "api",
  "style": {
    "source_port": "south",
    "source_offset": 0.5,
    "target_port": "north",
    "target_offset": 0.75
  }
}
```

The generated draw.io file contains editable waypoints, while the SVG preview and validator consume the same route plan. See the [routing contract](skills/drawio-diagram-engineer/references/routing.md), [source IR](skills/drawio-diagram-engineer/assets/example.routing.json), [editable example](docs/routing/checkout-routing.drawio), [SVG preview](docs/routing/main.svg), and [100-point audit](docs/routing/audit.json).

![Explicit ports and automatic fan-out routing](docs/routing/main.svg)

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
drawio_tool.py erd <erd.json|schema.sql> -o <erd.drawio> [--ir-output <ir.json>] [--preview-dir <dir>]
drawio_tool.py ha <ha.json> -o <ha.drawio> [--ir-output <ir.json>] [--preview-dir <dir>]
drawio_tool.py import <source> --type <python|typescript|openapi|sql|compose|terraform|kubernetes|github-actions|gitlab-ci> -o <ir.json>
drawio_tool.py diff <baseline.ir.json> <candidate.ir.json> -o <report.json> [--diagram-output <drift.drawio>] [--preview-dir <dir>] [--fail-on-drift]
drawio_tool.py patch <ir.json> <operations.json> -o <updated.json>
drawio_tool.py preview <ir.json> -o <preview.svg> [--page <id>] [--theme-file <theme.json>]
drawio_tool.py audit <ir.json|blueprint.json|diagram.drawio> [-o <report.json>] [--preview-dir <dir>] [--strict]
drawio_tool.py validate <ir.json|diagram.drawio> [--strict]
drawio_tool.py inspect <diagram.drawio>
drawio_tool.py render <diagram.drawio> -o <output.png|svg|pdf|jpg> [--embed]
```

JSON works without third-party packages. YAML input is optional and requires PyYAML.

## Roadmap

The v0.3–v0.8 feature roadmap is complete. The next milestone focuses on the v1 compatibility policy, migration rules, cross-platform Desktop integration, security auditing, installation tests, and reproducible signed releases. See [ROADMAP.md](ROADMAP.md).

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
