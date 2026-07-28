#!/usr/bin/env python3
"""Create a deterministic Agent Skill zip and SHA-256 checksum."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "drawio-diagram-engineer"
IGNORED_PARTS = {"__pycache__", ".DS_Store"}
IGNORED_SUFFIXES = {".pyc"}


def included_files() -> list[Path]:
    return sorted(
        (
            path
            for path in SKILL.rglob("*")
            if path.is_file()
            and not (set(path.relative_to(SKILL).parts) & IGNORED_PARTS)
            and path.suffix not in IGNORED_SUFFIXES
        ),
        key=lambda path: path.relative_to(SKILL).as_posix(),
    )


def package(output: Path) -> str:
    output_location = output.absolute()
    if output.suffix.lower() != ".zip":
        raise ValueError("output must use a .zip extension")
    if SKILL.absolute() in output_location.parents:
        raise ValueError("output must be outside the skill source directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
    ) as archive:
        for source in included_files():
            relative = Path(SKILL.name) / source.relative_to(SKILL)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if os.access(source, os.X_OK) else 0o644) << 16
            info.create_system = 3
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="utf-8",
    )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "dist" / "drawio-diagram-engineer.zip",
    )
    args = parser.parse_args()
    try:
        digest = package(args.output)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{args.output}\nsha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
