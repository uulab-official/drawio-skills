#!/usr/bin/env python3
"""Verify a signed release tag and its version contract."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIGNERS = ROOT / ".github/release-signers"
SEMVER_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def read_version(path: Path, pattern: str, label: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise ValueError(f"cannot read {label} version from {path}")
    return match.group(1)


def verify_release_tag(
    repo: Path,
    tag: str,
    allowed_signers: Path,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def fail(code: str, message: str) -> None:
        findings.append({"level": "error", "code": code, "message": message})

    report: dict[str, Any] = {
        "format": "drawio-release-tag-verification/v1",
        "tag": tag,
        "annotated": False,
        "signed": False,
        "version_consistent": False,
        "target": None,
        "principal": None,
        "fingerprint": None,
        "passed": False,
        "findings": findings,
    }
    match = SEMVER_TAG.fullmatch(tag)
    if not match:
        fail("tag.semver", "release tag must use canonical vMAJOR.MINOR.PATCH syntax")
        return report
    version = tag[1:]

    object_type = git(repo, "cat-file", "-t", f"refs/tags/{tag}")
    if object_type.returncode != 0:
        fail("tag.missing", "release tag does not exist")
        return report
    report["annotated"] = object_type.stdout.strip() == "tag"
    if not report["annotated"]:
        fail("tag.annotated", "release tag must be an annotated tag object")
        return report

    target_result = git(repo, "rev-list", "-n", "1", tag)
    if target_result.returncode != 0:
        fail("tag.target", "release tag target cannot be resolved")
        return report
    report["target"] = target_result.stdout.strip()

    if not allowed_signers.is_file():
        fail("tag.signers", "allowed signers file is missing")
        return report
    signature = git(
        repo,
        "-c", "gpg.format=ssh",
        "-c", f"gpg.ssh.allowedSignersFile={allowed_signers.resolve()}",
        "verify-tag", "--raw", tag,
    )
    signature_output = "\n".join((signature.stdout, signature.stderr))
    if signature.returncode != 0:
        fail("tag.signature", "release tag signature is missing or untrusted")
    else:
        report["signed"] = True
        principal_match = re.search(
            r'Good "git" signature for ([^ ]+)', signature_output
        )
        fingerprint_match = re.search(r"(SHA256:[A-Za-z0-9+/=]+)", signature_output)
        if principal_match:
            report["principal"] = principal_match.group(1)
        if fingerprint_match:
            report["fingerprint"] = fingerprint_match.group(1)

    try:
        versions = {
            "pyproject": read_version(
                repo / "pyproject.toml",
                r'^version\s*=\s*"([^"]+)"',
                "pyproject",
            ),
            "tool": read_version(
                repo / "skills/drawio-diagram-engineer/scripts/drawio_tool.py",
                r'^VERSION\s*=\s*"([^"]+)"',
                "tool",
            ),
        }
        changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError as exc:
        fail("tag.version-files", f"version contract file is unavailable: {exc}")
        return report
    report["versions"] = versions
    mismatched = [
        name for name, declared in versions.items()
        if declared != version
    ]
    if mismatched:
        fail(
            "tag.version",
            f"tag {tag} does not match: {', '.join(sorted(mismatched))}",
        )
    elif not re.search(
        rf"^## {re.escape(version)}(?:\s|—|-)", changelog, re.MULTILINE
    ):
        fail("tag.changelog", f"CHANGELOG.md has no {version} release heading")
    else:
        report["version_consistent"] = True

    subject = git(repo, "for-each-ref", "--format=%(subject)", f"refs/tags/{tag}")
    if subject.returncode != 0 or subject.stdout.strip() != tag:
        fail("tag.subject", f"signed tag subject must be exactly {tag}")

    report["passed"] = not findings
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--allowed-signers", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo = args.repo.resolve()
    signers = (
        args.allowed_signers.resolve()
        if args.allowed_signers
        else repo / ".github/release-signers"
    )
    try:
        report = verify_release_tag(repo, args.tag, signers)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
