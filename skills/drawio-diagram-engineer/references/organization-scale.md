# Organization-scale trust, discovery, and interoperability

Use this workflow when review authority spans teams, evidence spans repositories, or governance data must enter an observability system. Every adapter remains file based and deterministic. The core engine does not contact an identity provider, metrics endpoint, or Structurizr service.

## Delegated reviewer trust

`verify-delegated-approvals` adds a dated organization trust policy over an existing `drawio-approval-ledger/v1`. A delegation binds exact reviewer principals and roles to teams, an inclusive `valid_from` and exclusive `valid_until` UTC window, and one trust-root-relative OpenSSH allowed-signers file.

```bash
python3 scripts/drawio_tool.py verify-delegated-approvals review \
  --ledger approvals.json \
  --trust-policy review-trust.json \
  --trust-root .github/review-trust \
  -o delegated-approval-report.json
```

The verifier independently checks:

- the ledger's review binding, hash chain, event IDs, and revocations;
- exactly one active delegation for each event's principal, role, and timestamp;
- every event signature against the delegation's dated allowed-signers file;
- the pinned SHA-256 of each allowed-signers file;
- unique active reviewers, minimum approvals, required roles, and required teams.

Rotate a key by creating a new allowed-signers file and a non-overlapping delegation window. Keep the prior file available while historical events remain verifiable. Do not edit a pinned file in place. Overlapping matching delegations fail closed because an event must resolve to exactly one trust epoch.

The policy contract is [review-trust.schema.json](review-trust.schema.json). Verification emits [delegated-approval-report.schema.json](delegated-approval-report.schema.json) and exits `15` when integrity or organization quorum fails. [example.review-trust.json](../assets/example.review-trust.json) shows the format.

## Append-only transparency

`transparency-log` hashes canonical JSON governance artifacts as domain-separated Merkle leaves and stores an inclusion proof for every entry:

```bash
python3 scripts/drawio_tool.py transparency-log \
  architecture-catalog.json approvals.json governance-trends.json \
  -o transparency-log.json

python3 scripts/drawio_tool.py verify-transparency-log transparency-log.json
```

To extend a published log, pass it as a baseline:

```bash
python3 scripts/drawio_tool.py transparency-log new-snapshot.json \
  --baseline transparency-log.json \
  -o transparency-log.next.json
```

Baseline entries must remain an exact prefix. A repeated `(name, format)` coordinate may retain its digest but cannot change it. New entries are sorted before append, so identical inputs produce identical roots. The verifier recomputes every leaf, proof, and root and exits `16` on tampering. The format is [transparency-log.schema.json](transparency-log.schema.json).

This is a portable proof bundle, not a hosted witness service. Publish successive roots through an independently controlled release, transparency service, or audit channel when third-party consistency evidence is required.

## Searchable architecture portal

Generate a static portal from a `drawio-evidence-catalog/v1`:

```bash
python3 scripts/drawio_tool.py catalog-portal architecture-catalog.json \
  -o architecture-portal --title "Platform Architecture"
```

The output contains `index.html`, `portal.js`, the exact `catalog.json`, local favicon/social-preview SVGs, and a [versioned manifest](architecture-portal.schema.json). Search runs locally over title, repository, source path, and revision. There are no remote fonts, trackers, frameworks, or runtime API requests. The output directory uses an ownership marker and atomic replacement.

Serve the directory as static files or open `index.html` locally. A source evidence link appears only when the catalog contains an explicit HTTP(S) `source_url`.

## Prometheus and OpenTelemetry metrics

Convert a `drawio-governance-trends/v1` history without sending it:

```bash
python3 scripts/drawio_tool.py export-governance-metrics \
  governance-trends.json \
  --prometheus governance.prom \
  --otlp governance.otlp.json \
  --report governance-metrics.json
```

Prometheus text contains the latest snapshot as gauges with repository, source path, and revision labels. OTLP JSON contains every dated snapshot as gauge data points at UTC midnight. The tool writes transport-neutral artifacts; use an authenticated collector or deployment pipeline to transmit them. The report contract is [governance-metrics.schema.json](governance-metrics.schema.json).

## Structurizr and C4 exchange

Import a Structurizr workspace JSON model:

```bash
python3 scripts/drawio_tool.py import-structurizr workspace.json \
  -o architecture.blueprint.json
python3 scripts/drawio_tool.py blueprint architecture.blueprint.json \
  -o architecture.drawio --strict
```

People map to actors; software systems, containers, and components preserve their hierarchy; model-level and element-level relationships map to synchronous Blueprint relations. Unsupported workspace views, styles, deployment nodes, and properties remain outside this bounded adapter.

Export a Blueprint for adjacent tooling:

```bash
python3 scripts/drawio_tool.py export-structurizr \
  architecture.blueprint.json -o workspace.json
```

The export includes a `drawioAdapter` provenance block described by [structurizr-adapter.schema.json](structurizr-adapter.schema.json). Start with [example.structurizr.json](../assets/example.structurizr.json).

## Markdown ADR exchange

Export Blueprint decisions to a guarded directory:

```bash
python3 scripts/drawio_tool.py export-adrs architecture.blueprint.json \
  -o docs/decisions
```

Each Markdown file contains a stable `ADR-ID`, status, decision body, and comma-separated `Affects` line. The generated `adr-index.json` pins every file digest.

Import one file or all `*.md` files in a directory:

```bash
python3 scripts/drawio_tool.py import-adrs docs/decisions \
  --blueprint architecture.blueprint.json \
  -o architecture.with-decisions.json
```

With `--blueprint`, imported decisions replace the model's decision list and every affected element must exist. Without it, the result is a standalone `drawio-adr-adapter/v1` document. See [adr-adapter.schema.json](adr-adapter.schema.json) and [example.adr.md](../assets/example.adr.md).
