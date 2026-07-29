# Security

Read this reference before importing untrusted diagrams, publishing a bundle, changing XML decoding, or handling infrastructure definitions that may contain credentials.

## Security gate

Run:

```bash
python3 <skill-dir>/scripts/drawio_tool.py security <model|diagram.drawio|bundle> \
  -o security.json --strict
```

`build` runs the same scan against normalized Diagram IR and writes `security.json` into every successful bundle.

For `.drawio` input, the scanner covers visible labels and links plus hidden `data-*` page and cell attributes used by [round-trip editing](round-trip.md). Moving text out of a visible label does not hide it from the gate.

The scanner rejects:

- scalar values under credential-like keys;
- inline password, token, secret, API-key, or client-secret assignments;
- common credential prefixes and embedded private keys;
- `javascript:`, `vbscript:`, and `file:` links;
- XML DTD and entity declarations;
- compressed draw.io pages above the decompression safety limit.

Placeholder values such as `${TOKEN}`, `<redacted>`, `example`, and masked asterisks are allowed.

HTTP, HTTPS, and mail links are listed in `external_links` for human review but are not errors. The tool does not fetch them.

## Data handling

- Build bundles contain normalized IR but never copy the original input.
- Kubernetes Secret payload values are excluded by the importer.
- Security reports name locations and rule codes but never echo suspected secret values.
- Rendering invokes draw.io Desktop without a shell.
- JSON workflows require no third-party runtime package.
- Published review sites contain no scripts or remote assets and apply a restrictive Content Security Policy.
- Reviewer updates, carried annotations, policy messages, ownership labels, repository coordinates, and revision labels are HTML-escaped before publication; SARIF, policy, ownership, and provenance evidence are JSON encoded.
- Policy packs never execute code, fetch links, or read artifacts outside the owned bundle and explicitly supplied local files.
- Ownership and policy selectors are bounded local glob matches. The publisher validates source/public URLs as HTTP(S) but never fetches them.
- Markdown summaries escape table and link syntax before writing reviewer-controlled content.

## Boundaries

The scan is a deterministic release gate, not a replacement for repository secret scanning, malware analysis, or organizational threat modeling. Scan source repositories with the organization’s security tooling before import.

Structured JSON/YAML and raw XML are limited to 50 MiB. Each decompressed draw.io page is limited to 100 MiB. The XML parser also rejects DTD/entity declarations. Inputs above a limit require manual review before increasing it.

## Supply-chain verification

Tagged release workflows build the skill ZIP from the tag, publish a SHA-256 checksum, and generate a GitHub artifact provenance attestation. Verify a downloaded release with:

```bash
shasum -a 256 -c drawio-diagram-engineer-<version>.zip.sha256
gh attestation verify drawio-diagram-engineer-<version>.zip \
  --repo uulab-official/drawio-skills
```

Maintainers also sign release tags with the SSH key trusted by the repository's `.github/release-signers`. From a repository clone, run `python3 scripts/verify_release_tag.py <tag>` before trusting the tag-to-source binding. Published GitHub releases are immutable, so their associated tag and assets cannot be replaced after publication.
