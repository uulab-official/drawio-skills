# Desktop export and verification

Read this reference when a user requests a PNG, SVG, PDF, or JPEG rendered by draw.io Desktop, when Desktop discovery fails, or when maintaining the cross-platform integration workflow.

## Local export

Run `doctor` first. Desktop discovery checks the usual application paths on macOS, Windows, and Linux. Override discovery with `DRAWIO_DESKTOP_BINARY` or `render --binary` when the executable is portable, installed per-user, or mounted elsewhere.

```bash
python3 <skill-dir>/scripts/drawio_tool.py render diagram.drawio \
  -o diagram.png --width 2400 --report diagram.export.json
```

`render` disables Desktop auto-update for the invocation, uses a shell-free argument vector, waits up to 90 seconds, and then validates the artifact. It writes to a same-directory temporary file and atomically replaces the requested output only after verification succeeds, so a failed export does not destroy the previous artifact.

## Independent verification

Validate an export received from another machine without launching Desktop:

```bash
python3 <skill-dir>/scripts/drawio_tool.py verify-export diagram.svg \
  -o diagram.export.json
```

The `drawio-export-report/v1` contract is defined by [export-report.schema.json](export-report.schema.json). Checks include:

- PNG signature, IHDR dimensions, and terminal IEND chunk.
- SVG root, no entity/internal-DTD declarations, positive dimensions or viewBox, and drawable content. A standard external SVG doctype is accepted without resolving it.
- PDF header and terminal EOF marker.
- JPEG start- and end-of-image markers.
- Declared format versus detected signature for every artifact.

These are deterministic structural checks, not pixel-level visual approval. Inspect important final exports visually in addition to passing `verify-export`.

## Continuous integration

The repository pins an official `jgraph/drawio-desktop` release, asset URL, byte size, and SHA-256 for Linux x64, macOS universal, and Windows x64 in `.github/drawio-desktop-lock.json`. `scripts/desktop_lock.py` validates the lock and verifies each download before installation.

The `Desktop Integration` workflow runs on relevant `main` changes, every Monday, and manual dispatch. Each hosted operating system compiles the same editable source, exports SVG, PNG, PDF, and JPEG through the real Desktop executable, validates each result, and uploads the exports plus reports for 14 days.

Update the lock only from the official GitHub release record. Review all asset names, sizes, and digests, run `desktop_lock.py validate`, and let all three integration jobs pass before merging.

## Failure handling

- Exit `4`: Desktop was not found. Set `DRAWIO_DESKTOP_BINARY` or pass `--binary`.
- Exit `2` before export: input, format, filesystem, launch, or timeout failure.
- Exit `2` after export: Desktop returned but the artifact failed structural verification. Keep the generated report for diagnosis.
- Linux without a display: invoke the tool under `xvfb-run -a`.
- If Desktop export remains unavailable, deliver the editable `.drawio` and dependency-free SVG preview and state that the native export was skipped.
