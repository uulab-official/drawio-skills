# CLI reference

Read this reference when composing commands, automating the tool, or interpreting exit codes. All paths are local. Commands print JSON except `doctor` in its default human format and fatal errors on stderr.

## Guided workflow

```text
doctor [--format human|json]
init <profile> [-o <starter>] [--force]
build <model|source> [-o <bundle-dir>] [--type <type>] [--name <name>]
      [--title <title>] [--theme-file <theme.json>] [--max-files 500]
      [--strict] [--force]
merge-annotations <prior-review|annotations.json> <updates.json>
                  -o <merged.json> [--force]
policy-test <tests.json> [-o <report.json>] [--baseline <report.json>]
            [--fail-on-change] [--strict] [--force]
publish <bundle-dir> -o <review-dir> [--title <title>]
        [--annotations <annotations.json>] [--carry-review <prior-review>]
        [--baseline <review|bundle>] [--policy <policy.json>]...
        [--ownership <ownership.json>] [--codeowners <CODEOWNERS>]
        [--evaluation-date <YYYY-MM-DD>]
        [--source-revision <revision>] [--source-repository <repository>]
        [--source-url <https-url>] [--source-path <repository-path>]
        [--public-base-url <https-url>] [--github-checks]
        [--fail-on-visual-change] [--fail-on-policy]
        [--fail-on-unowned-findings] [--strict] [--force]
attest-review <review-dir> --signing-key <private-key>
              [--namespace <name>] [--force]
verify-review-attestation <review-dir> --allowed-signers <file>
                          --identity <principal> [--namespace <name>]
record-approval <review-dir> --ledger <ledger.json> --identity <principal>
                --role <role> --timestamp <UTC> --reason <text>
                --signing-key <private-key> [--action approve|revoke]
                [--allowed-signers <file>]
                [--revokes <event-id>] [--minimum-approvals <n>]
                [--required-role <role>]...
verify-approval-ledger <review-dir> --ledger <ledger.json>
                       --allowed-signers <file> [--namespace <name>]
catalog-reviews <review-dir>... -o <catalog.json>
                [--baseline <catalog.json>] [--fail-on-change] [--force]
governance-trends --snapshot <YYYY-MM-DD=review-dir>... -o <trends.json>
                  [--csv-output <trends.csv>] [--force]
rule-provider-request <review-dir> -o <request.json> [--force]
verify-rule-provider-result <request.json> <result.json>
                            [-o <report.json>] [--force]
verify-delegated-approvals <review-dir> --ledger <ledger.json>
                           --trust-policy <trust.json> --trust-root <dir>
                           [--namespace <name>] [-o <report.json>] [--force]
transparency-log <artifact.json>... -o <log.json>
                 [--baseline <log.json>] [--force]
verify-transparency-log <log.json>
catalog-portal <catalog.json> -o <portal-dir> [--title <title>] [--force]
export-governance-metrics <trends.json>
                          [--prometheus <metrics.prom>] [--otlp <metrics.json>]
                          [--report <report.json>] [--force]
import-structurizr <workspace.json> -o <blueprint.json> [--force]
export-structurizr <blueprint.json> -o <workspace.json> [--force]
import-adrs <adr.md|directory> -o <decisions.json>
            [--blueprint <blueprint.json>] [--max-files 500] [--force]
export-adrs <blueprint.json> -o <adr-directory> [--force]
```

`init` profiles: `architecture`, `blueprint`, `erd`, `ha`, `routing`, `terraform`, `kubernetes`, `github-actions`, and `gitlab-ci`.

`build` types: `auto`, `diagram`, `blueprint`, `erd`, `sql-erd`, `ha`, `python`, `typescript`, `openapi`, `sql`, `compose`, `terraform`, `kubernetes`, `github-actions`, and `gitlab-ci`.

`merge-annotations` replaces matching stable IDs with full-record updates and carries all untouched reviewer records. `publish --carry-review` performs the same merge against a regenerated diagram and validates every page/cell link.

`policy-test` evaluates compact synthetic review cases without building diagrams. Every case requires an explicit date. `--strict` requires assertions to cover every composed rule and exception; `--baseline --fail-on-change` exits `10` when deterministic outcome fingerprints change.

`publish` creates an atomic, script-free HTML/SVG review site from a bundle. Repeat `--policy` to compose organization and team packs. Scoped exceptions use the deterministic `--evaluation-date`; when omitted, `SOURCE_DATE_EPOCH` or the current UTC date is used. `--ownership` routes SARIF findings first; `--codeowners` supplies fallback owners for the repository-relative `--source-path`. `--github-checks` emits a maximum of 50 source annotations and requires a full SCM revision plus repository. `--public-base-url` makes evidence links absolute. Source revision defaults to `GITHUB_SHA`, then `CI_COMMIT_SHA`, then the bundle digest. See [collaborative-review.md](collaborative-review.md).

Every site includes an unsigned in-toto statement. `attest-review` signs it as `reports/attestation.json.sig` with the default `drawio-review` OpenSSH namespace. `verify-review-attestation` first recomputes the manifest/provenance binding, then verifies the signature against the supplied allowed-signers file.

`record-approval` appends an OpenSSH-signed, hash-chained approval or same-reviewer revocation. Quorum and required roles are immutable after ledger creation. Appending requires `--allowed-signers` so the signer verifies the entire existing chain and the new event before writing. `verify-approval-ledger` recomputes the review binding, event IDs, chain, signatures, active approvals, required roles, and quorum; it exits `12` when integrity or quorum fails.

`catalog-reviews` verifies each review attestation before indexing its immutable repository/path/revision coordinate. A conflicting digest at the same coordinate is rejected. Baseline discovery drift exits `14` when `--fail-on-change` is set.

`governance-trends` exports dated audit, policy, ownership, exception, annotation, and SARIF metrics for one repository path. Dates are explicit so JSON and optional CSV remain deterministic.

The rule-provider protocol never executes provider code. `rule-provider-request` emits bounded review facts. Run an organization provider in a separately configured sandbox, then pass only its `drawio-rule-provider-result/v1` JSON to `verify-rule-provider-result`. The verifier checks the request digest, provider identity, bounds, page/cell selectors, result levels, and emits normalized SARIF; error-level rule failures exit `13`.

`verify-delegated-approvals` resolves each signed event to exactly one principal/role/time delegation, verifies the pinned allowed-signers epoch, maps active approvals to organization teams, and applies organization quorum. It exits `15` on any integrity, role, team, or quorum failure.

`transparency-log` records canonical governance-document digests as SHA-256 Merkle leaves. A baseline is retained as an exact prefix; an existing name/format coordinate cannot change digest. `verify-transparency-log` recomputes the entry leaves, inclusion proofs, and root and exits `16` on tampering.

`catalog-portal` atomically builds a local searchable static site from an evidence catalog. `export-governance-metrics` writes the latest snapshot as Prometheus gauges and all snapshots as OTLP JSON; at least one transport output is required.

`import-structurizr` maps people, systems, containers, components, and relationships into a Blueprint. `export-structurizr` creates a bounded Structurizr workspace with adapter provenance. `export-adrs` writes Markdown decisions plus a digest index; `import-adrs --blueprint` replaces decisions only after every `Affects` semantic ID validates. See [organization-scale.md](organization-scale.md).

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
extract <diagram.drawio> -o <ir.json> [--report <report.json>] [--strict]
import <source> -o <ir.json> [--type <type>] [--title <title>] [--max-files 500]
patch <ir.json> <operations.json> -o <updated.json>
diff <baseline.json> <candidate.json> -o <report.json>
     [--diagram-output <drift.drawio>] [--preview-dir <dir>] [--fail-on-drift]
```

`extract` recovers Diagram IR v1 from compressed or uncompressed draw.io. Compiler-generated files retain page, group, node, edge, ERD, and HA semantics through versioned metadata. Legacy files use deterministic best-effort inference. `--strict` exits `3` when the report is not lossless; see [round-trip.md](round-trip.md) and [extraction-report.schema.json](extraction-report.schema.json).

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
| `7` | Visual baseline change found with `publish --fail-on-visual-change` |
| `8` | Architecture policy error found with `publish --fail-on-policy` |
| `9` | One or more findings lack an owner with `publish --fail-on-unowned-findings` |
| `10` | Policy assertions, strict coverage, or requested baseline stability failed |
| `11` | Review attestation binding or signature verification failed |
| `12` | Approval-ledger integrity, signature, revocation, or quorum verification failed |
| `13` | Rule-provider result integrity or error-level organization rule failed |
| `14` | Evidence-catalog discovery changed with `catalog-reviews --fail-on-change` |
| `15` | Delegated trust integrity, organization mapping, or quorum verification failed |
| `16` | Transparency-log leaf, inclusion proof, or Merkle-root verification failed |
