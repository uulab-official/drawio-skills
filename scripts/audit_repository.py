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
    return {
        "format": "drawio-repository-audit/v1",
        "passed": not findings,
        "runtime_dependencies": required_imports,
        "optional_dependencies": optional_imports,
        "workflow_actions": actions,
        "unpinned_actions": unpinned_actions,
        "missing_files": missing_files,
        "findings": findings,
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
