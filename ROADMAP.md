# Roadmap

The project advances through measurable quality gates, not feature-count alone. A milestone is complete only when its behavior is documented, deterministic, and covered by tests.

## v0.1 — Deterministic foundation

- [x] Versioned Diagram IR
- [x] Stable semantic cell IDs
- [x] Deterministic LR/TB layout
- [x] Editable uncompressed `.drawio` output
- [x] Compressed and uncompressed `.drawio` inspection
- [x] Structural validator and 0–100 strict quality gate
- [x] Light, dark, and colorblind-safe themes

## v0.2 — Reviewable workflows

- [x] Group-aware layout without overlapping regions
- [x] Atomic semantic IR patch operations
- [x] OpenAPI, SQL DDL, and Docker Compose importers
- [x] Multi-page compilation with click-through links
- [x] Direct-route node and edge-crossing risk analysis
- [x] Dependency-free SVG review preview
- [x] CI coverage across Python 3.9, 3.12, and 3.13

## v0.3 — Repository and infrastructure intelligence

- [x] Python and TypeScript import-graph extraction
- [x] Terraform and Kubernetes resource importers
- [x] GitHub Actions and GitLab CI pipeline importers
- [x] Diagram diff and architecture-drift view
- [ ] Explicit port assignment and stronger orthogonal routing
- [x] Five-case deterministic fixture corpus for each Terraform, Kubernetes, GitHub Actions, and GitLab CI importer
- [ ] Expand the five-case fixture corpus to every legacy importer

Exit criteria: at least five fixture projects per importer, deterministic snapshots, no strict validation failures, bounded output for repositories above 500 source files, and explicit routing controls. The infrastructure/CI importer cohort meets its fixture and strict-validation gates; legacy importer expansion and routing remain.

## v0.4 — Architecture blueprints

- [x] Architecture Blueprint Generator with five coordinated operational views
- [x] System → Container → Component hierarchy projection
- [x] Domain, deployment, and security-zone view projection
- [x] Multi-level C4-style context and logical views

## v0.5 — Design systems, decisions, and visual QA

- [x] Validated draw.io shape registry with license provenance
- [x] Organization theme tokens and reusable style packs
- [x] Automated WCAG contrast and text-density checks
- [x] Structured SVG review manifest with targeted repair suggestions
- [x] Architecture decision view linked to affected elements
- [x] End-to-end theme, audit, and six-page Blueprint fixtures

Exit criteria: WCAG-aware palettes, verified shape resolution, structured before/after repair guidance, and deterministic six-view Blueprint generation.

## v0.6 — Data modeling and high availability

- [x] Field-level entity nodes with PK, FK, UK, type, nullable, and default metadata
- [x] Official draw.io Crow's Foot relationship markers
- [x] ERD cardinality, key, field-reference, arity, and type compatibility validation
- [x] Direct SQL DDL → editable ERD generation
- [x] HA topology grouped by explicit failure domains
- [x] Replication, heartbeat, traffic, and quorum edge semantics
- [x] Deterministic failover scenario lanes with health checks, RTO, and RPO
- [x] HA validation for cross-domain promotion, replica counts, quorum, and stateful replication
- [x] Editable ERD/HA examples, SVG reviews, audits, schemas, and CI workflows

Exit criteria: ERD and HA examples score 100 without warnings, regenerate byte-identically, preserve domain semantics in editable draw.io XML, and pass all supported Python versions.

## v0.7 — Infrastructure intelligence and drift

- [x] Dependency-free Terraform block and direct-reference extraction
- [x] Namespace-aware Kubernetes topology with selector, backend, configuration, storage, and ownership relations
- [x] Secret-safe Kubernetes import that excludes payload values
- [x] GitHub Actions workflow/job and GitLab CI stage/job projection
- [x] Semantic page, group, node, and edge comparison that ignores layout-only changes
- [x] Machine-readable drift report with an editable, non-color-only drift view
- [x] Twenty infrastructure/CI fixture projects with deterministic strict-valid snapshots
- [x] Editable Terraform, Kubernetes, GitHub Actions, GitLab CI, and drift examples

Exit criteria: all four importers remain deterministic and bounded, every new importer has at least five strict-valid fixtures, Secret values are absent from generated IR, drift has a CI failure mode, public examples score 100 without warnings, and all supported Python versions pass.

## v1.0 — Stable public contract

- [ ] Freeze Diagram IR v1 compatibility policy
- [ ] Publish migration and deprecation rules
- [ ] Cross-platform draw.io Desktop integration tests
- [ ] Security and dependency audit
- [ ] Installation tests for Codex and other Agent Skills-compatible clients
- [ ] Reproducible release artifacts and signed tags

The v1.0 release requires zero known critical defects, deterministic output across supported Python versions, and complete documentation for every public command.
