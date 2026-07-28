# Security policy

## Reporting

Please report suspected vulnerabilities privately through GitHub Security Advisories for this repository. Do not include secrets, proprietary diagrams, or production infrastructure data in a public issue.

## Scope

The compiler reads local JSON, optional YAML, and `.drawio` XML. The render command invokes a locally installed draw.io Desktop binary. Treat all input as untrusted:

- run the tool with least privilege;
- review diagrams before sharing them;
- avoid embedding credentials or sensitive metadata;
- keep draw.io Desktop and Python patched.

No telemetry or network requests are performed by the compiler, validator, or inspector.

The Kubernetes importer never copies `Secret.data` or `Secret.stringData` values into Diagram IR. It emits resource metadata and a redaction notice only. Other resource names, namespaces, image/runtime descriptions, Terraform addresses, and pipeline job names can still be sensitive; inspect generated IR before publishing it.
