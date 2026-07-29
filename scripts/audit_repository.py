#!/usr/bin/env python3
"""Audit runtime dependencies and release workflow integrity."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STDLIB_IMPORTS = {
    "__future__",
    "argparse",
    "ast",
    "base64",
    "collections",
    "copy",
    "datetime",
    "fnmatch",
    "hashlib",
    "html",
    "importlib",
    "json",
    "math",
    "os",
    "pathlib",
    "re",
    "shutil",
    "subprocess",
    "sys",
    "tempfile",
    "typing",
    "unittest",
    "urllib",
    "xml",
    "zipfile",
    "zlib",
}
OPTIONAL_IMPORTS = {"yaml"}
ACTION_PATTERN = re.compile(r"^\s*(?:-\s+)?uses:\s+([^@\s]+)@([^\s#]+)", re.MULTILINE)


def python_imports() -> tuple[list[str], list[str]]:
    runtime_files = [
        ROOT / "skills/drawio-diagram-engineer/scripts/drawio_tool.py",
        ROOT / "scripts/audit_repository.py",
        ROOT / "scripts/install_skill.py",
        ROOT / "scripts/package_skill.py",
        ROOT / "scripts/desktop_lock.py",
        ROOT / "scripts/verify_release_tag.py",
    ]
    required: set[str] = set()
    optional: set[str] = set()
    for path in runtime_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".", 1)[0]]
            else:
                continue
            for name in names:
                if name in OPTIONAL_IMPORTS:
                    optional.add(name)
                elif name not in STDLIB_IMPORTS:
                    required.add(name)
    return sorted(required), sorted(optional)


def workflow_actions() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    actions: list[dict[str, str]] = []
    unpinned: list[dict[str, str]] = []
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for name, reference in ACTION_PATTERN.findall(text):
            record = {
                "workflow": path.name,
                "action": name,
                "reference": reference,
            }
            actions.append(record)
            if not re.fullmatch(r"[0-9a-f]{40}", reference):
                unpinned.append(record)
    return actions, unpinned


def audit() -> dict[str, object]:
    required_imports, optional_imports = python_imports()
    actions, unpinned_actions = workflow_actions()
    required_files = [
        ROOT / "LICENSE",
        ROOT / "SECURITY.md",
        ROOT / "skills/drawio-diagram-engineer/LICENSE.txt",
        ROOT / "skills/drawio-diagram-engineer/references/security.md",
        ROOT / "skills/drawio-diagram-engineer/references/compatibility.md",
        ROOT / ".github/release-signers",
    ]
    missing_files = [
        str(path.relative_to(ROOT))
        for path in required_files
        if not path.is_file()
    ]
    findings = []
    if required_imports:
        findings.append({
            "level": "error",
            "code": "dependency.undeclared",
            "message": f"unclassified runtime imports: {', '.join(required_imports)}",
        })
    if unpinned_actions:
        findings.append({
            "level": "error",
            "code": "workflow.unpinned-action",
            "message": f"{len(unpinned_actions)} workflow actions are not pinned to commits",
        })
    if missing_files:
        findings.append({
            "level": "error",
            "code": "distribution.missing-file",
            "message": f"missing required files: {', '.join(missing_files)}",
        })
    release_workflow = (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    release_contracts = {
        "signed-tag-gate": 'python scripts/verify_release_tag.py "$RELEASE_TAG"',
        "complete-tag-history": "fetch-depth: 0",
        "draft-release": "--draft",
        "explicit-publish": 'gh release edit "$RELEASE_TAG" --draft=false',
    }
    missing_release_contracts = [
        name for name, token in release_contracts.items()
        if token not in release_workflow
    ]
    if missing_release_contracts:
        findings.append({
            "level": "error",
            "code": "release.missing-contract",
            "message": (
                "release workflow is missing: "
                + ", ".join(missing_release_contracts)
            ),
        })
    return {
        "format": "drawio-repository-audit/v1",
        "passed": not findings,
        "runtime_dependencies": required_imports,
        "optional_dependencies": optional_imports,
        "workflow_actions": actions,
        "unpinned_actions": unpinned_actions,
        "missing_files": missing_files,
        "release_contracts": {
            name: name not in missing_release_contracts
            for name in release_contracts
        },
        "findings": findings,
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
