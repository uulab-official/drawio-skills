#!/usr/bin/env python3
"""Validate and securely download the pinned draw.io Desktop CI release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / ".github/drawio-desktop-lock.json"
PLATFORMS = {"linux-x64", "macos-universal", "windows-x64"}


def load_lock() -> dict[str, Any]:
    data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if data.get("format") != "drawio-desktop-lock/v1":
        raise ValueError("unsupported draw.io Desktop lock format")
    if data.get("repository") != "jgraph/drawio-desktop":
        raise ValueError("Desktop lock must use the official jgraph/drawio-desktop repository")
    release = str(data.get("release", ""))
    platforms = data.get("platforms")
    if not release.startswith("v") or not isinstance(platforms, dict):
        raise ValueError("Desktop lock requires a versioned release and platform map")
    if set(platforms) != PLATFORMS:
        raise ValueError(f"Desktop lock platforms must be: {', '.join(sorted(PLATFORMS))}")
    release_prefix = (
        f"https://github.com/jgraph/drawio-desktop/releases/download/{release}/"
    )
    for platform_name in sorted(platforms):
        item = platforms[platform_name]
        if not isinstance(item, dict):
            raise ValueError(f"{platform_name} lock entry must be an object")
        asset = str(item.get("asset", ""))
        if item.get("url") != release_prefix + asset:
            raise ValueError(f"{platform_name} asset URL is not pinned to {release}")
        if (
            not isinstance(item.get("sha256"), str)
            or len(item["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in item["sha256"])
        ):
            raise ValueError(f"{platform_name} SHA-256 is invalid")
        if not isinstance(item.get("size"), int) or item["size"] <= 0:
            raise ValueError(f"{platform_name} size is invalid")
    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_download(path: Path, item: dict[str, Any]) -> None:
    if path.stat().st_size != item["size"]:
        raise ValueError(
            f"download size mismatch: got {path.stat().st_size}, expected {item['size']}"
        )
    actual = sha256(path)
    if actual != item["sha256"]:
        raise ValueError(f"download SHA-256 mismatch: got {actual}")


def download(platform_name: str, output: Path) -> None:
    item = load_lock()["platforms"][platform_name]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", dir=output.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        request = urllib.request.Request(
            item["url"],
            headers={"User-Agent": "uulab-drawio-skills-desktop-integration"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                shutil.copyfileobj(response, temporary, length=1024 * 1024)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        verify_download(temporary_path, item)
        temporary_path.replace(output)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate the committed lock file")
    show = subparsers.add_parser("show", help="print one platform lock entry")
    show.add_argument("platform", choices=sorted(PLATFORMS))
    fetch = subparsers.add_parser("download", help="download and verify one pinned asset")
    fetch.add_argument("platform", choices=sorted(PLATFORMS))
    fetch.add_argument("-o", "--output", required=True)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        lock = load_lock()
        if args.command == "validate":
            print(json.dumps({
                "valid": True,
                "release": lock["release"],
                "platforms": sorted(lock["platforms"]),
            }, indent=2))
        elif args.command == "show":
            print(json.dumps(lock["platforms"][args.platform], indent=2))
        else:
            output = Path(args.output)
            download(args.platform, output)
            print(json.dumps({
                "platform": args.platform,
                "output": str(output),
                "sha256": lock["platforms"][args.platform]["sha256"],
            }, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
