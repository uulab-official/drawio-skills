# Changelog

All notable changes are documented here. The project follows semantic versioning after the 1.0 public contract is frozen.

## 1.2.0 — 2026-07-29

- Add `publish` to create atomic, script-free multi-page HTML/SVG review sites from complete bundles.
- Add stable SVG fragment anchors for every semantic group, node, and edge with target highlighting.
- Add versioned reviewer annotations with strict page/cell link validation.
- Add a machine-readable evidence index for audit, security, extraction, native exports, and visual regression.
- Add deterministic page-level visual baselines with CI exit code `7`.
- Block unsafe publication, refuse unowned output replacement, and publish without scripts, remote assets, telemetry, or network requests.
- Fix round-trip extraction for semantic IDs beginning with `node-`, `edge-`, `group-`, or `page-`.

## 1.1.0 — 2026-07-28

- Embed versioned, deterministic Diagram IR metadata in generated draw.io pages and semantic cells.
- Add `extract` for compressed and uncompressed `.drawio` → Diagram IR round-trip recovery.
- Preserve multi-page links, ERD fields and cardinalities, HA semantics, positions, sizes, endpoints, and supported styles.
- Add deterministic best-effort recovery for legacy and hand-authored diagrams with an explicit strict inference gate.
- Publish the machine-readable `drawio-extraction-report/v1` schema and round-trip editing contract.
- Extend credential scanning to hidden page and cell metadata so round-trip state cannot bypass security checks.
- Regenerate all nine checked-in editable examples with v1.1 metadata and verify strict extraction.

## 1.0.0 — 2026-07-28

- Declare Diagram IR v1 and all documented CLI commands stable under the published compatibility policy.
- Add a committed SSH allowed-signers trust root and a machine-readable signed-tag verifier.
- Reject unsigned, lightweight, untrusted, non-semantic, and version-inconsistent release tags before packaging.
- Build release assets in draft state and publish only after tests, checksums, provenance attestations, and uploads succeed.
- Enable immutable GitHub releases so published tags and assets cannot be moved, replaced, or deleted independently.
- Complete the stable public-contract roadmap after cross-platform native Desktop export validation.

## 0.11.0 — 2026-07-28

- Pin official draw.io Desktop v31.0.2 assets by URL, byte size, and GitHub-published SHA-256 for Linux x64, macOS universal, and Windows x64.
- Add real weekly, manual, and relevant-main-change Desktop integration tests across all three hosted operating systems.
- Export and retain SVG, PNG, PDF, and JPEG artifacts plus verification reports from each platform.
- Add `verify-export` and the machine-readable `drawio-export-report/v1` contract.
- Make `render` disable Desktop auto-update, validate temporary output, atomically publish passing artifacts, and optionally persist a report.
- Add bounded safe-SVG, PNG structure/dimensions, PDF terminator, JPEG marker, and declared-format checks.
- Complete the v1 cross-platform Desktop integration roadmap item.

## 0.10.0 — 2026-07-28

- Publish Diagram IR v1 compatibility, additive-change, deprecation, and bundle-evolution policies.
- Add deterministic migration for unversioned and version 0 Diagram IR with CI `--check` mode and machine-readable reports.
- Add machine-readable bundle, security-report, and migration-report schemas.
- Add a `security` gate for suspected credentials, private keys, unsafe links, DTD/entities, and decompression limits without echoing secret values.
- Add `security.json` to every successful one-command build bundle.
- Bound structured input plus raw and compressed draw.io XML parsing to resist oversized and decompression-bomb inputs.
- Add macOS, Windows, and Linux Desktop discovery contracts plus `DRAWIO_DESKTOP_BINARY` and `render --binary`.
- Pin all GitHub Actions to commit hashes and add repository dependency/workflow auditing.
- Add tagged release automation with deterministic ZIPs, SHA-256 checksums, and GitHub/Sigstore provenance attestations.
- Expand the test suite across migration, security, XML hardening, cross-platform discovery, and bundle publication paths.

## 0.9.0 — 2026-07-28

- Add `doctor` with machine-readable core readiness and optional YAML/Desktop capability reporting.
- Add guarded `init` starters for architecture, Blueprint, ERD, HA, routing, infrastructure, and CI diagrams.
- Add one-command `build` bundles containing normalized IR, editable draw.io, every SVG page, audit results, and a versioned manifest.
- Default `.sql` builds to field-level Crow's Foot ERDs while retaining the generic SQL dependency importer.
- Add safe bundle replacement that refuses to overwrite directories not owned by the tool.
- Add a self-checking copy/symlink installer for Agent Skills-compatible clients.
- Add byte-reproducible ZIP packaging with SHA-256 checksums.
- Add onboarding, bundle-contract, exit-code, and troubleshooting documentation plus installation and distribution tests.

## 0.8.0 — 2026-07-28

- Add explicit north/east/south/west edge ports and optional normalized endpoint offsets.
- Add deterministic fan-out/fan-in port distribution.
- Add obstacle-aware orthogonal route selection with editable draw.io waypoints.
- Make SVG previews and draw.io validation consume the same planned routes.
- Upgrade routing checks from center-line risk estimates to actual waypoint segment analysis.
- Add five deterministic strict-valid fixtures for every Python, TypeScript, OpenAPI, SQL, and Compose importer, bringing the importer corpus to 45 cases.
- Publish a 100-point editable routing example and complete the v0.3 repository/infrastructure milestone.

## 0.7.0 — 2026-07-28

- Add bounded, deterministic Terraform resource/data/module importing with direct-reference dependency edges.
- Add namespace-aware Kubernetes importing for ingress routing, service selectors, workloads, configuration, Secrets, storage, and owner references.
- Redact Kubernetes Secret values by construction.
- Add GitHub Actions and GitLab CI pipeline importers with prerequisite-to-dependent execution flow.
- Add semantic Diagram IR diff reports and editable architecture-drift views with CI `--fail-on-drift`.
- Add a versioned drift report schema, 20-case infrastructure/CI fixture corpus, and 100-point editable examples.

## 0.6.0 — 2026-07-28

- Add a field-level ERD model, schema, validator, SQL DDL importer, and Crow's Foot renderer.
- Add entity rows for PK, FK, UK, data type, nullability, and defaults.
- Add HA topology and failover models with explicit failure domains, replicas, replication modes, health checks, RTO, and RPO.
- Add HA resilience checks for quorum shape, stateful replication, and cross-domain promotion.
- Publish deterministic editable ERD and HA example packs with 100-point audits.

## 0.5.0 — 2026-07-28

- Add six-page Architecture Blueprint packs with a linked Architecture Decisions view.
- Add reusable organization theme packs and a machine-readable theme schema.
- Add an Apache-2.0-provenance shape registry backed by official JGraph shape identifiers.
- Add WCAG 4.5:1 contrast and text-density checks.
- Add `audit` reports with generated-geometry checks, grouped repairs, SVG previews, and a visual-review checklist.
- Publish an editable, deterministic Commerce Platform example pack with a 100-point audit.

## 0.4.0

- Add coordinated context, logical, data, deployment, and security Blueprint views.
- Add hierarchy, domain, deployment-target, and trust-zone projection.

## 0.3.0

- Add Python and TypeScript/JavaScript import-graph extraction.

## 0.2.0

- Add semantic patching, source importers, multi-page links, SVG previews, and strict quality scoring.

## 0.1.0

- Add Diagram IR v1, deterministic layout, editable draw.io compilation, and structural validation.
