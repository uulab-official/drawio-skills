# Governance lifecycle and federation

Read this reference when approvals must survive review-site regeneration, multiple repositories need a common evidence index, governance metrics feed dashboards, or organization rules live outside the core policy vocabulary.

## Signed approval ledger

Create the ledger with explicit quorum and roles. Every timestamp must be UTC and end in `Z`.

```bash
python3 <skill-dir>/scripts/drawio_tool.py record-approval build/review \
  --ledger build/review-approvals.json \
  --identity architect@example.com \
  --role architecture \
  --timestamp 2026-07-29T03:00:00Z \
  --reason "Architecture reviewed" \
  --signing-key ~/.ssh/architecture-review \
  --minimum-approvals 2 \
  --required-role architecture \
  --required-role security
```

Append another approval with the same command, omit the quorum arguments, and pass `--allowed-signers .github/architecture-reviewers`. Appending verifies the complete existing chain plus the new signature before replacing the ledger. Approval events bind the exact `review.json`, review attestation, source revision, source path, and bundle digest. Each event signs its identity, role, action, reason, timestamp, sequence, and prior-event digest.

Revoke only the same reviewer's prior active approval:

```bash
python3 <skill-dir>/scripts/drawio_tool.py record-approval build/review \
  --ledger build/review-approvals.json \
  --identity architect@example.com \
  --role architecture \
  --timestamp 2026-07-29T04:00:00Z \
  --reason "Architecture changed after approval" \
  --action revoke \
  --revokes <approval-event-sha256> \
  --signing-key ~/.ssh/architecture-review \
  --allowed-signers .github/architecture-reviewers
```

Verify the full ledger before deployment:

```bash
python3 <skill-dir>/scripts/drawio_tool.py verify-approval-ledger build/review \
  --ledger build/review-approvals.json \
  --allowed-signers .github/architecture-reviewers
```

Use OpenSSH allowed-signers entries scoped to the `drawio-approval` namespace. Do not edit quorum, event order, reviewer identity, role, reason, timestamps, or signatures by hand. Regenerated review evidence intentionally invalidates the prior ledger subject; start a new ledger for the new immutable review.

## Multi-repository evidence catalog

Build one deterministic catalog from independently published review directories:

```bash
python3 <skill-dir>/scripts/drawio_tool.py catalog-reviews \
  services/orders/review services/payments/review \
  -o build/architecture-catalog.json
```

The command recomputes every review attestation and indexes repository, source path, revision, review digest, attestation digest, bundle digest, and gate status. The same repository/path/revision coordinate cannot resolve to different evidence.

Use `--baseline prior-catalog.json --fail-on-change` when repository discovery is itself controlled. Store catalogs in an immutable artifact store or publish them alongside governance dashboards.

## Governance trend exports

Supply explicit snapshot dates and reviews for the same repository path:

```bash
python3 <skill-dir>/scripts/drawio_tool.py governance-trends \
  --snapshot 2026-06-30=history/june/review \
  --snapshot 2026-07-29=history/july/review \
  -o build/governance-trends.json \
  --csv-output build/governance-trends.csv
```

Metrics cover audit scores and findings, policy errors and warnings, ownership coverage and unassigned findings, open annotations, SARIF findings, and applied or expired exceptions. Snapshot dates are labels supplied by the caller; preserve the corresponding immutable review directories.

## Sandboxed JSON rule providers

The diagram engine does not import, launch, or shell out to organization rule providers. It only produces and validates JSON:

```bash
python3 <skill-dir>/scripts/drawio_tool.py rule-provider-request build/review \
  -o build/provider-request.json

# Run the provider outside the engine in an organization-managed sandbox.

python3 <skill-dir>/scripts/drawio_tool.py verify-rule-provider-result \
  build/provider-request.json build/provider-result.json \
  -o build/provider-report.json
```

The provider result must bind the canonical request SHA-256 and identify its provider and version. Results may reference only pages and cells exposed by the request, are limited to 1,000 entries, and use `error`, `warning`, or `note`. Failed results become portable SARIF. Error-level failures exit `13`; warnings remain visible without failing the gate.

Treat providers and their runtime as untrusted:

- Run them in a separate container, job, or restricted service account.
- Deny repository credentials and network access unless the provider explicitly requires them.
- Pass only the generated request, never the source repository or private review keys.
- Retain the request, result, validated report, provider image digest, and sandbox policy as evidence.
