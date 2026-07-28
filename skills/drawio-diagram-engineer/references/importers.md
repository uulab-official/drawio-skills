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

## Limits

Importers intentionally summarize rather than reproduce every source field. Preserve the source separately. Do not infer runtime traffic, security boundaries, dynamic language imports, or undeclared dependencies.
