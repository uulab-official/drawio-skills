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
- [ ] Terraform and Kubernetes resource importers
- [ ] GitHub Actions and GitLab CI pipeline importers
- [ ] Diagram diff and architecture-drift view
- [ ] Explicit port assignment and stronger orthogonal routing
- [ ] Importer fixture corpus with real-world edge cases

Exit criteria: at least five fixture projects per importer, deterministic snapshots, no strict validation failures, and bounded output for repositories above 500 source files.

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

## v1.0 — Stable public contract

- [ ] Freeze Diagram IR v1 compatibility policy
- [ ] Publish migration and deprecation rules
- [ ] Cross-platform draw.io Desktop integration tests
- [ ] Security and dependency audit
- [ ] Installation tests for Codex and other Agent Skills-compatible clients
- [ ] Reproducible release artifacts and signed tags

The v1.0 release requires zero known critical defects, deterministic output across supported Python versions, and complete documentation for every public command.
