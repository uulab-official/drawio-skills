#!/usr/bin/env python3
"""Install drawio-diagram-engineer into an Agent Skills directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "drawio-diagram-engineer"
SKILL_NAME = "drawio-diagram-engineer"


def default_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return Path(codex_home) / "skills" if codex_home else Path.home() / ".codex" / "skills"


def validate_skill(path: Path) -> None:
    required = [
        path / "SKILL.md",
        path / "LICENSE.txt",
        path / "agents" / "openai.yaml",
        path / "scripts" / "drawio_tool.py",
        path / "references" / "diagram-ir.schema.json",
    ]
    missing = [str(item.relative_to(path)) for item in required if not item.is_file()]
    if missing:
        raise ValueError(f"invalid skill source; missing: {', '.join(missing)}")
    frontmatter = (path / "SKILL.md").read_text(encoding="utf-8").splitlines()[:5]
    if f"name: {SKILL_NAME}" not in frontmatter:
        raise ValueError(f"SKILL.md does not declare name: {SKILL_NAME}")


def remove_existing(destination: Path) -> None:
    if destination.is_symlink():
        destination.unlink()
        return
    validate_skill(destination)
    shutil.rmtree(destination)


def install(target_root: Path, mode: str, force: bool) -> dict[str, object]:
    validate_skill(SOURCE)
    destination = target_root / SKILL_NAME
    source_location = SOURCE.absolute()
    destination_location = destination.absolute()
    if destination_location == source_location or source_location in destination_location.parents:
        raise ValueError("target must not be the skill source directory or one of its children")
    target_root.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if not force:
            raise ValueError(f"{destination} already exists; pass --force to replace this skill")
        if not destination.is_symlink():
            validate_skill(destination)
    staging_root = Path(tempfile.mkdtemp(prefix=".drawio-skill-install-", dir=str(target_root)))
    candidate = staging_root / SKILL_NAME
    try:
        if mode == "symlink":
            candidate.symlink_to(SOURCE.resolve(), target_is_directory=True)
        else:
            shutil.copytree(
                SOURCE,
                candidate,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
            )
        completed = subprocess.run(
            [
                sys.executable,
                str(candidate / "scripts" / "drawio_tool.py"),
                "doctor",
                "--format",
                "json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout or "installed skill failed doctor")
        doctor = json.loads(completed.stdout)
        if destination.exists() or destination.is_symlink():
            remove_existing(destination)
        candidate.replace(destination)
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)
    return {
        "installed": str(destination),
        "mode": mode,
        "ready": doctor["ready"],
        "restart_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        default=default_skills_dir(),
        help="skills directory (default: CODEX_HOME/skills or ~/.codex/skills)",
    )
    parser.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        result = install(args.target.expanduser(), args.mode, args.force)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
