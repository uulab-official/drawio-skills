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

The `security` command scans models, `.drawio` files, and bundles for embedded credential patterns, private keys, unsafe URL schemes, prohibited XML declarations, and decompression-limit violations. Successful `build` bundles include `security.json`. Findings name locations but never echo suspected credential values.

Structured JSON/YAML and uncompressed draw.io input are limited to 50 MiB; each compressed page is limited to 100 MiB after decompression. DTD and entity declarations are rejected before XML parsing.

Release workflows use only first-party GitHub actions pinned to full commit hashes. The workflow rejects tags that do not carry a trusted SSH signature or whose semantic version differs from the packaged source. Tagged ZIP artifacts include SHA-256 checksums and GitHub/Sigstore provenance attestations. Published GitHub releases are immutable.

Verify all three layers:

```bash
python3 scripts/verify_release_tag.py v1.0.0
shasum -a 256 -c drawio-diagram-engineer-1.0.0.zip.sha256
gh attestation verify drawio-diagram-engineer-1.0.0.zip \
  --repo uulab-official/drawio-skills
```

The committed release signer fingerprint is `SHA256:/R76WEgWRbF5O5LxcoUjz0ocIsKCp+Rq8AlT3JIjssE`.

The Kubernetes importer never copies `Secret.data` or `Secret.stringData` values into Diagram IR. It emits resource metadata and a redaction notice only. Other resource names, namespaces, image/runtime descriptions, Terraform addresses, and pipeline job names can still be sensitive; inspect generated IR before publishing it.
