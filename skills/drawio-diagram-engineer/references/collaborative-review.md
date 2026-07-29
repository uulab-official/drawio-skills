# Collaborative review publication

Read this reference when a bundle must be shared with reviewers or used as a CI architecture artifact without requiring draw.io Desktop.

## Publish a review site

Build first, then publish:

```bash
python3 <skill-dir>/scripts/drawio_tool.py build architecture.json \
  -o build/architecture --strict

python3 <skill-dir>/scripts/drawio_tool.py publish build/architecture \
  -o build/architecture-review --strict
```

The output is an atomic, portable folder:

```text
architecture-review/
├── index.html
├── review.json
├── pages/
│   └── <page-id>.svg
└── reports/
    ├── audit.json
    ├── security.json
    ├── extraction.json
    ├── policy.json
    └── findings.sarif
```

Open `index.html` directly or serve the folder with any static file server. It contains no JavaScript, remote assets, telemetry, or network requests. A restrictive Content Security Policy permits only local SVG frames and inline CSS.

Every SVG group has a stable fragment anchor:

- `#node-<semantic-id>`
- `#edge-<semantic-id>`
- `#group-<semantic-id>`

Opening a fragment highlights the target. The HTML page links audit findings and supplied annotations to these anchors.

## Add review annotations

Pass a file conforming to [review-annotations.schema.json](review-annotations.schema.json):

```json
{
  "version": "1",
  "annotations": [
    {
      "id": "confirm-boundary",
      "page": "context",
      "cell": "api-gateway",
      "status": "open",
      "author": "Architecture Review",
      "message": "Confirm ownership at this boundary."
    }
  ]
}
```

`cell` accepts either a semantic ID or an explicit `node-*`, `edge-*`, or `group-*` anchor. Ambiguous and unknown references fail publication rather than creating dead links. Status is `open`, `accepted`, or `resolved`.

Use [example.review-annotations.json](../assets/example.review-annotations.json) as a starting point.

## Carry decisions across regeneration

Carry only human reviewer annotations from a prior site, then apply full-record updates by stable annotation ID:

```bash
python3 <skill-dir>/scripts/drawio_tool.py publish build/architecture \
  -o build/current-review \
  --carry-review build/prior-review \
  --annotations annotation-updates.json \
  --strict
```

Matching update IDs replace prior records, so changing `status` to `accepted` or `resolved` persists the decision without editing generated HTML. New IDs are added; untouched prior IDs are carried. Publication fails if a carried page or cell no longer exists, forcing an explicit reviewer decision instead of silently dropping context.

To create a standalone merged source file:

```bash
python3 <skill-dir>/scripts/drawio_tool.py merge-annotations \
  build/prior-review annotation-updates.json \
  -o annotations.merged.json
```

Use [example.review-annotation-updates.json](../assets/example.review-annotation-updates.json) for the full-record update shape.

## Visual baselines

Compare against an approved review site or bundle:

```bash
python3 <skill-dir>/scripts/drawio_tool.py publish build/architecture \
  -o build/current-review \
  --baseline approved-review \
  --fail-on-visual-change
```

The publisher hashes deterministic SVG bytes per page and classifies pages as `added`, `removed`, `changed`, or `unchanged`. Exit code `7` means a visual change was found. The site is still written so CI can retain it for diagnosis.

This is deterministic regression detection, not perceptual image comparison. A tool-version layout improvement can intentionally change the baseline; review the result before approving the new site.

## Evidence and gates

`review.json` conforms to [review-site.schema.json](review-site.schema.json) and indexes:

- audit score, errors, and warnings;
- persisted and live security status;
- draw.io extraction losslessness and semantic alignment with bundle IR;
- optional native export verification reports;
- visual baseline status;
- annotations and all semantic elements.

`publish --strict` exits `3` for a weak audit, non-lossless extraction, IR/draw.io semantic mismatch, or failed export report. Security errors and invalid bundle structure block publication with exit `2`.

## Architecture policy and SARIF

Apply a policy conforming to [architecture-policy.schema.json](architecture-policy.schema.json):

```bash
python3 <skill-dir>/scripts/drawio_tool.py publish build/architecture \
  -o build/architecture-review \
  --policy architecture-policy.json \
  --fail-on-policy \
  --strict
```

Rules can require pages, a minimum audit score, security, lossless extraction, semantic alignment, verified native export formats, a visual baseline, or a maximum number of open reviewer annotations. Error-level failures produce exit `8`; warning-level failures remain visible without blocking publication. Start with [production-review.json](../assets/policies/production-review.json).

Every publication writes [policy-report.schema.json](policy-report.schema.json)-compatible `reports/policy.json` and SARIF 2.1.0 `reports/findings.sarif`. SARIF includes audit, security, extraction, visual, policy, and open reviewer findings with stable fingerprints and page/cell logical locations.

For hosted publication and code-scanning upload, read [github-pages-publication.md](github-pages-publication.md) and copy the pinned workflow asset.

## Safe replacement

`publish` refuses non-empty output directories. `--force` only replaces a directory whose `review.json` identifies it as a `drawio-review-site/v1` generated by this skill. It never replaces an arbitrary user directory.
