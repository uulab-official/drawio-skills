# Source importers

Convert source material to Diagram IR before compiling. Always inspect the generated IR and reduce scope when it exceeds roughly 20 nodes.

## Python and TypeScript

```bash
python3 <skill-dir>/scripts/drawio_tool.py import ./src \
  --type python -o modules.diagram.json

python3 <skill-dir>/scripts/drawio_tool.py import ./src \
  --type typescript -o modules.diagram.json
```

Scan internal module imports, ignore dependency/build directories, and group modules by top-level directory. TypeScript mode also accepts JavaScript and resolves relative imports, re-exports, `require()`, and dynamic `import()`. External packages remain out of scope.

The default limit is 500 matching files. Raise `--max-files` explicitly only after narrowing the intended view; large graphs should be split by package or bounded context.

## OpenAPI

```bash
python3 <skill-dir>/scripts/drawio_tool.py import openapi.json \
  --type openapi -o api.diagram.json
```

Create one API node, operation nodes, schema nodes, and `uses` relations derived from `$ref`. JSON works without dependencies; YAML requires PyYAML.

## SQL DDL

```bash
python3 <skill-dir>/scripts/drawio_tool.py import schema.sql \
  --type sql -o schema.diagram.json
```

Parse `CREATE TABLE`, inline and table-level primary keys, and foreign-key references. Treat tables referenced but not declared in the input as external nodes.

## Docker Compose

```bash
python3 <skill-dir>/scripts/drawio_tool.py import compose.yaml \
  --type compose -o compose.diagram.json
```

Create service and named-volume nodes. Derive dependency edges from `depends_on` and data edges from named-volume mounts. Use `--type auto` when the source format is unambiguous.

## Terraform

```bash
python3 <skill-dir>/scripts/drawio_tool.py import ./infrastructure \
  --type terraform -o terraform.diagram.json
```

Scan `.tf` files and create nodes for `resource`, `data`, and `module` blocks. Direct HCL references become `depends on` edges. Resources are classified into service, data, queue, or external styles from their addresses. The parser is deliberately dependency-free and bounded; it does not evaluate expressions, modules, variables, `for_each`, provider state, or generated configuration.

Use semantic Terraform addresses as the source of truth. A diagram edge means that a direct address reference exists in the scanned block, not that Terraform has produced the same dependency in a plan.

## Kubernetes

```bash
python3 <skill-dir>/scripts/drawio_tool.py import ./manifests \
  --type kubernetes -o kubernetes.diagram.json
```

Import JSON or YAML manifest streams, including Kubernetes `List` objects and multi-document YAML. Resources are grouped by namespace. The importer derives:

- Ingress and HTTPRoute backends to Services.
- Service selectors to Deployment, StatefulSet, DaemonSet, Job, CronJob, or Pod labels.
- Workload references to ConfigMaps, Secrets, and PersistentVolumeClaims.
- Owner-reference edges when both resources are present.

Secret payloads are never copied into Diagram IR; only kind, name, namespace, and a redaction notice are retained. YAML requires PyYAML, while JSON remains standard-library-only.

## GitHub Actions

```bash
python3 <skill-dir>/scripts/drawio_tool.py import . \
  --type github-actions -o github-actions.diagram.json
```

Read workflow files from `.github/workflows` when a repository root is supplied. Jobs are grouped by workflow, `needs` becomes a directed edge from the prerequisite job to the dependent job, and job-level `uses` links to a reusable workflow node. Runtime matrix expansion, step-level shell behavior, environments, permissions, and conditional execution remain outside the diagram.

## GitLab CI

```bash
python3 <skill-dir>/scripts/drawio_tool.py import . \
  --type gitlab-ci -o gitlab-ci.diagram.json
```

Read `.gitlab-ci.yml`, `.gitlab-ci.yaml`, JSON equivalents, or an explicitly supplied file. Jobs are grouped by stage. Explicit `needs` or `dependencies` take precedence; otherwise the importer connects adjacent stages to show the default stage barrier. Hidden templates and reserved top-level configuration are excluded.

## Detection and deterministic limits

`--type auto` detects Terraform directories, `.github/workflows`, repository-root GitLab CI files, `.tf` and `.sql` files, Kubernetes objects, OpenAPI, Compose, and single GitHub/GitLab pipeline documents when the shape is unambiguous. Use an explicit type for directories containing several ecosystems.

All tree and directory importers enforce `--max-files 500` by default. Every output is sorted by source path and semantic address so recompiling the same input is byte-identical.

## Limits

Importers intentionally summarize rather than reproduce every source field. Preserve the source separately. Do not infer runtime traffic, security boundaries, dynamic language imports, or undeclared dependencies.
