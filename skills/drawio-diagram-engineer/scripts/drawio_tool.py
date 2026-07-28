#!/usr/bin/env python3
"""Deterministic Diagram IR compiler and draw.io quality tool."""

from __future__ import annotations

import argparse
import ast
import base64
import copy
import html
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

VERSION = "1.1.0"
IR_VERSION = "1"
IR_METADATA_VERSION = "1"
BUNDLE_FORMAT = "drawio-diagram-bundle/v1"
MAX_STRUCTURED_INPUT_BYTES = 50 * 1024 * 1024
MAX_XML_INPUT_BYTES = 50 * 1024 * 1024
MAX_DECOMPRESSED_PAGE_BYTES = 100 * 1024 * 1024
ALLOWED_DIRECTIONS = {"LR", "TB"}
ALLOWED_THEMES = {"light", "dark", "colorblind"}
ALLOWED_KINDS = {
    "client", "service", "database", "queue", "external", "decision",
    "process", "document", "note", "entity",
}
ALLOWED_EDGE_KINDS = {"sync", "async", "data", "dependency", "association"}
ALLOWED_PORTS = {"auto", "north", "east", "south", "west"}
ALLOWED_BLUEPRINT_SCOPES = {
    "actor", "external", "system", "container", "component", "data", "infrastructure",
}
ALLOWED_BLUEPRINT_VIEWS = {"context", "logical", "data", "deployment", "security", "decisions"}
ALLOWED_DECISION_STATUS = {"proposed", "accepted", "deprecated", "superseded"}
ALLOWED_CARDINALITIES = {"one", "zero-or-one", "one-or-many", "zero-or-many"}
CARDINALITY_MARKERS = {
    "one": "ERmandOne",
    "zero-or-one": "ERzeroToOne",
    "one-or-many": "ERoneToMany",
    "zero-or-many": "ERzeroToMany",
}
CARDINALITY_LABELS = {
    "one": "1",
    "zero-or-one": "0..1",
    "one-or-many": "1..*",
    "zero-or-many": "0..*",
}
ALLOWED_HA_ROLES = {
    "active", "standby", "active-active", "replica", "quorum",
    "load-balancer", "witness", "client",
}
ALLOWED_HA_LINK_MODES = {
    "traffic", "sync-replication", "async-replication", "heartbeat", "quorum",
}
ALLOWED_FAILURE_DOMAIN_LEVELS = {"region", "zone", "rack", "node"}
TOP_LEVEL_FIELDS = {"version", "diagram", "groups", "nodes", "edges", "pages"}
DIAGRAM_FIELDS = {"title", "direction", "theme", "theme_tokens", "gap", "background"}
PAGE_FIELDS = {"id", "title", "diagram", "groups", "nodes", "edges"}
GROUP_FIELDS = {"id", "label"}
NODE_FIELDS = {
    "id", "label", "kind", "group", "description", "position", "size",
    "style", "link", "fields",
}
EDGE_FIELDS = {"id", "from", "to", "label", "kind", "style"}
EDGE_STYLE_FIELDS = {
    "color", "dashed", "width", "start_cardinality", "end_cardinality",
    "source_port", "target_port", "source_offset", "target_offset",
}

THEMES = {
    "light": {
        "background": "#ffffff", "group_fill": "#f8fafc", "group_stroke": "#94a3b8",
        "font": "#0f172a", "edge": "#475569",
        "client": ("#e0f2fe", "#0284c7"), "service": ("#ede9fe", "#7c3aed"),
        "database": ("#dcfce7", "#16a34a"), "queue": ("#fef3c7", "#d97706"),
        "external": ("#f1f5f9", "#64748b"), "decision": ("#ffe4e6", "#e11d48"),
        "process": ("#dbeafe", "#2563eb"), "document": ("#fae8ff", "#c026d3"),
        "note": ("#fef9c3", "#ca8a04"), "entity": ("#f8fafc", "#334155"),
    },
    "dark": {
        "background": "#0f172a", "group_fill": "#1e293b", "group_stroke": "#64748b",
        "font": "#f8fafc", "edge": "#cbd5e1",
        "client": ("#164e63", "#38bdf8"), "service": ("#4c1d95", "#a78bfa"),
        "database": ("#14532d", "#4ade80"), "queue": ("#78350f", "#fbbf24"),
        "external": ("#334155", "#94a3b8"), "decision": ("#881337", "#fb7185"),
        "process": ("#1e3a8a", "#60a5fa"), "document": ("#701a75", "#e879f9"),
        "note": ("#713f12", "#fde047"), "entity": ("#1e293b", "#94a3b8"),
    },
    "colorblind": {
        "background": "#ffffff", "group_fill": "#f7f7f7", "group_stroke": "#7a7a7a",
        "font": "#111111", "edge": "#4d4d4d",
        "client": ("#d9f0d3", "#009e73"), "service": ("#d6e5f3", "#0072b2"),
        "database": ("#fff2cc", "#e69f00"), "queue": ("#fce4d6", "#d55e00"),
        "external": ("#eeeeee", "#666666"), "decision": ("#f4cccc", "#cc79a7"),
        "process": ("#cfe2f3", "#56b4e9"), "document": ("#eadcf8", "#8b5cf6"),
        "note": ("#fff2cc", "#b8860b"), "entity": ("#f7f7f7", "#4d4d4d"),
    },
}

THEME_COLOR_KEYS = {"background", "group_fill", "group_stroke", "font", "edge"}
THEME_KIND_KEYS = set(ALLOWED_KINDS)
VERIFIED_SHAPES = {
    "rectangle", "cylinder3", "message", "rhombus", "process", "document", "note",
}
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
SKILL_DIR = ASSET_DIR.parent
_SHAPE_REGISTRY: dict[str, Any] | None = None


def load_data(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_STRUCTURED_INPUT_BYTES:
        raise ValueError(
            f"structured input exceeds {MAX_STRUCTURED_INPUT_BYTES // (1024 * 1024)} MiB safety limit"
        )
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError("YAML input requires PyYAML; use JSON or install pyyaml") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("root value must be an object")
    return data


def is_hex_color(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def hex_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def relative_luminance(value: str) -> float:
    channels = []
    for channel in hex_rgb(value):
        normalized = channel / 255
        channels.append(normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    left, right = relative_luminance(first), relative_luminance(second)
    lighter, darker = max(left, right), min(left, right)
    return (lighter + 0.05) / (darker + 0.05)


def validate_theme_tokens(tokens: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(tokens, dict):
        return [issue("error", "theme.tokens", "theme tokens must be an object")]
    for key in sorted(THEME_COLOR_KEYS):
        if not is_hex_color(tokens.get(key)):
            issues.append(issue("error", "theme.color", f"{key} must be a 6-digit hex color", key))
    for key in sorted(THEME_KIND_KEYS):
        pair = tokens.get(key)
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not all(is_hex_color(color) for color in pair)
        ):
            issues.append(issue("error", "theme.pair", f"{key} must contain fill and stroke colors", key))
            continue
        font = tokens.get("font")
        if is_hex_color(font):
            ratio = contrast_ratio(str(font), str(pair[0]))
            if ratio < 4.5:
                issues.append(issue(
                    "warning", "theme.contrast",
                    f"{key} text contrast is {ratio:.2f}:1; target at least 4.5:1", key,
                ))
    if is_hex_color(tokens.get("font")) and is_hex_color(tokens.get("background")):
        ratio = contrast_ratio(str(tokens["font"]), str(tokens["background"]))
        if ratio < 4.5:
            issues.append(issue(
                "warning", "theme.contrast",
                f"canvas text contrast is {ratio:.2f}:1; target at least 4.5:1", "background",
            ))
    return issues


def load_theme_pack(path: Path) -> dict[str, Any]:
    pack = load_data(path)
    if str(pack.get("version", "")) != "1" or not valid_semantic_id(str(pack.get("name", ""))):
        raise ValueError("theme pack requires version 1 and a kebab-case name")
    issues = validate_theme_tokens(pack.get("tokens"))
    errors = [item for item in issues if item["level"] == "error"]
    if errors:
        raise ValueError(f"invalid theme pack: {errors[0]['message']}")
    return copy.deepcopy(pack["tokens"])


def apply_theme_pack(data: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(data)
    result.setdefault("diagram", {})["theme_tokens"] = copy.deepcopy(tokens)
    return result


def resolve_theme(diagram: dict[str, Any]) -> dict[str, Any]:
    tokens = diagram.get("theme_tokens")
    if isinstance(tokens, dict):
        return tokens
    return THEMES[str(diagram.get("theme", "light"))]


def load_shape_registry() -> dict[str, Any]:
    global _SHAPE_REGISTRY
    if _SHAPE_REGISTRY is not None:
        return _SHAPE_REGISTRY
    registry = load_data(ASSET_DIR / "shape-registry.json")
    if str(registry.get("version", "")) != "1" or not isinstance(registry.get("shapes"), dict):
        raise ValueError("shape registry requires version 1 and shapes")
    provenance = registry.get("provenance", {})
    if provenance.get("license") != "Apache-2.0" or not str(provenance.get("source", "")).startswith("https://github.com/jgraph/"):
        raise ValueError("shape registry requires JGraph source and Apache-2.0 provenance")
    for kind in sorted(ALLOWED_KINDS):
        entry = registry["shapes"].get(kind)
        if not isinstance(entry, dict) or entry.get("shape") not in VERIFIED_SHAPES:
            raise ValueError(f"shape registry has no verified shape for {kind}")
        if not isinstance(entry.get("style"), dict):
            raise ValueError(f"shape registry style is invalid for {kind}")
    if registry.get("edge_markers") != CARDINALITY_MARKERS:
        raise ValueError("shape registry ER edge markers are incomplete or unverified")
    _SHAPE_REGISTRY = registry
    return registry


def issue(level: str, code: str, message: str, cell: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"level": level, "code": code, "message": message}
    if cell:
        item["cell"] = cell
    return item


def valid_semantic_id(value: str) -> bool:
    return re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is not None


def validate_ir(data: dict[str, Any], allow_page_links: bool = False) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in sorted(set(data) - TOP_LEVEL_FIELDS):
        issues.append(issue("warning", "ir.unknown-field", f"unknown top-level field: {field}"))
    if str(data.get("version", "")) != "1":
        issues.append(issue("error", "ir.version", "version must be \"1\""))
    if "pages" in data:
        pages = data.get("pages")
        if not isinstance(pages, list) or not pages:
            return issues + [issue("error", "pages.required", "pages must be a non-empty array")]
        page_ids: set[str] = set()
        defaults = data.get("diagram", {}) if isinstance(data.get("diagram"), dict) else {}
        for index, page in enumerate(pages):
            if not isinstance(page, dict) or not page.get("id") or not page.get("title"):
                issues.append(issue("error", "page.required", f"page {index} requires id and title"))
                continue
            page_id = str(page["id"])
            if not valid_semantic_id(page_id):
                issues.append(issue("error", "id.format", f"invalid page id: {page_id}", page_id))
            if page_id in page_ids:
                issues.append(issue("error", "page.duplicate", f"duplicate page id: {page_id}", page_id))
            page_ids.add(page_id)
            for field in sorted(set(page) - PAGE_FIELDS):
                issues.append(issue("warning", "page.unknown-field", f"unknown page field: {field}", page_id))
            page_diagram = page.get("diagram", {}) if isinstance(page.get("diagram"), dict) else {}
            page_data = {
                "version": "1",
                "diagram": {**defaults, **page_diagram, "title": page["title"]},
                "groups": page.get("groups", []),
                "nodes": page.get("nodes", []),
                "edges": page.get("edges", []),
            }
            for page_issue in validate_ir(page_data, allow_page_links=True):
                page_issue = dict(page_issue)
                page_issue["page"] = page_id
                issues.append(page_issue)
        for page in pages:
            if not isinstance(page, dict):
                continue
            for node in page.get("nodes", []) if isinstance(page.get("nodes"), list) else []:
                if isinstance(node, dict) and node.get("link") and node["link"] not in page_ids:
                    issues.append(issue(
                        "error", "node.link", f"unknown linked page: {node['link']}", str(node.get("id", ""))
                    ))
        return issues
    diagram = data.get("diagram", {})
    if not isinstance(diagram, dict):
        issues.append(issue("error", "ir.diagram", "diagram must be an object"))
        diagram = {}
    for field in sorted(set(diagram) - DIAGRAM_FIELDS):
        issues.append(issue("warning", "diagram.unknown-field", f"unknown diagram field: {field}"))
    direction = diagram.get("direction", "LR")
    if direction not in ALLOWED_DIRECTIONS:
        issues.append(issue("error", "ir.direction", "direction must be LR or TB"))
    theme = diagram.get("theme", "light")
    if theme not in ALLOWED_THEMES:
        issues.append(issue("error", "ir.theme", f"unknown theme: {theme}"))
    gap = diagram.get("gap", 100)
    if not isinstance(gap, int) or isinstance(gap, bool) or not 40 <= gap <= 400:
        issues.append(issue("error", "ir.gap", "gap must be an integer from 40 to 400"))
    background = diagram.get("background")
    if background is not None and (
        not isinstance(background, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", background) is None
    ):
        issues.append(issue("error", "ir.background", "background must be a 6-digit hex color"))
    if "theme_tokens" in diagram:
        issues.extend(validate_theme_tokens(diagram["theme_tokens"]))

    groups = data.get("groups", [])
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not isinstance(groups, list) or not isinstance(nodes, list) or not isinstance(edges, list):
        return issues + [issue("error", "ir.collections", "groups, nodes, and edges must be arrays")]

    group_ids: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or not group.get("id") or not group.get("label"):
            issues.append(issue("error", "group.required", "each group requires id and label"))
            continue
        for field in sorted(set(group) - GROUP_FIELDS):
            issues.append(issue("warning", "group.unknown-field", f"unknown group field: {field}", str(group["id"])))
        gid = str(group["id"])
        if not valid_semantic_id(gid):
            issues.append(issue("error", "id.format", f"invalid group id: {gid}", gid))
        if gid in group_ids:
            issues.append(issue("error", "id.duplicate", f"duplicate group id: {gid}", gid))
        group_ids.add(gid)

    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or not node.get("id") or not node.get("label"):
            issues.append(issue("error", "node.required", "each node requires id and label"))
            continue
        nid = str(node["id"])
        if not valid_semantic_id(nid):
            issues.append(issue("error", "id.format", f"invalid node id: {nid}", nid))
        for field in sorted(set(node) - NODE_FIELDS):
            issues.append(issue("warning", "node.unknown-field", f"unknown node field: {field}", nid))
        if nid in node_ids or nid in group_ids:
            issues.append(issue("error", "id.duplicate", f"duplicate id: {nid}", nid))
        node_ids.add(nid)
        kind = node.get("kind", "service")
        if kind not in ALLOWED_KINDS:
            issues.append(issue("warning", "node.kind", f"unknown kind {kind}; service style will be used", nid))
        if node.get("group") and node["group"] not in group_ids:
            issues.append(issue("error", "node.group", f"unknown group: {node['group']}", nid))
        position = node.get("position")
        if position is not None and (
            not isinstance(position, dict)
            or not all(isinstance(position.get(axis), (int, float)) and not isinstance(position.get(axis), bool) for axis in ("x", "y"))
        ):
            issues.append(issue("error", "node.position", "position requires numeric x and y", nid))
        size = node.get("size")
        if size is not None and (
            not isinstance(size, dict)
            or any(
                key in size and (
                    not isinstance(size[key], (int, float))
                    or isinstance(size[key], bool)
                    or size[key] <= 0
                )
                for key in ("width", "height")
            )
        ):
            issues.append(issue("error", "node.size", "size width and height must be positive numbers", nid))
        if node.get("link") and not allow_page_links:
            issues.append(issue("error", "node.link", "page links require multi-page IR", nid))
        fields = node.get("fields")
        if kind == "entity":
            if not isinstance(fields, list) or not fields:
                issues.append(issue("error", "entity.fields", "entity nodes require fields", nid))
            else:
                field_names: set[str] = set()
                for field_index, field in enumerate(fields):
                    if (
                        not isinstance(field, dict)
                        or not field.get("name")
                        or not field.get("type")
                    ):
                        issues.append(issue(
                            "error", "entity.field.required",
                            f"field {field_index} requires name and type", nid,
                        ))
                        continue
                    field_name = str(field["name"])
                    if field_name in field_names:
                        issues.append(issue(
                            "error", "entity.field.duplicate",
                            f"duplicate field: {field_name}", nid,
                        ))
                    field_names.add(field_name)
        elif fields is not None:
            issues.append(issue(
                "warning", "entity.fields",
                "fields are rendered only for entity nodes", nid,
            ))
        custom_style = node.get("style")
        if isinstance(custom_style, dict):
            for field in ("fill", "stroke", "font"):
                if field in custom_style and not is_hex_color(custom_style[field]):
                    issues.append(issue("error", "node.style.color", f"{field} must be a 6-digit hex color", nid))
            active_theme = resolve_theme(diagram)
            fill = custom_style.get("fill", active_theme.get(kind, active_theme["service"])[0])
            font = custom_style.get("font", active_theme["font"])
            if is_hex_color(fill) and is_hex_color(font):
                ratio = contrast_ratio(str(font), str(fill))
                if ratio < 4.5:
                    issues.append(issue(
                        "warning", "node.contrast",
                        f"text contrast is {ratio:.2f}:1; target at least 4.5:1", nid,
                    ))

    seen_edge_ids: set[str] = set()
    degrees: dict[str, int] = defaultdict(int)
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict) or not edge.get("from") or not edge.get("to"):
            issues.append(issue("error", "edge.required", f"edge {index} requires from and to"))
            continue
        source, target = str(edge["from"]), str(edge["to"])
        eid = str(edge.get("id", f"{source}-to-{target}-{index + 1}"))
        if not valid_semantic_id(eid):
            issues.append(issue("error", "id.format", f"invalid edge id: {eid}", eid))
        for field in sorted(set(edge) - EDGE_FIELDS):
            issues.append(issue("warning", "edge.unknown-field", f"unknown edge field: {field}", eid))
        if eid in seen_edge_ids or eid in node_ids or eid in group_ids:
            issues.append(issue("error", "id.duplicate", f"duplicate id: {eid}", eid))
        seen_edge_ids.add(eid)
        if source not in node_ids:
            issues.append(issue("error", "edge.source", f"unknown source: {source}", eid))
        if target not in node_ids:
            issues.append(issue("error", "edge.target", f"unknown target: {target}", eid))
        edge_style_data = edge.get("style", {}) if isinstance(edge.get("style"), dict) else {}
        is_erd_relation = (
            edge_style_data.get("start_cardinality") in ALLOWED_CARDINALITIES
            or edge_style_data.get("end_cardinality") in ALLOWED_CARDINALITIES
        )
        if source == target and not is_erd_relation:
            issues.append(issue("error", "edge.self-loop", "self-loops are not supported", eid))
        if edge.get("kind", "sync") not in ALLOWED_EDGE_KINDS:
            issues.append(issue("warning", "edge.kind", f"unknown edge kind: {edge.get('kind')}", eid))
        custom_edge_style = edge.get("style")
        if custom_edge_style is not None and not isinstance(custom_edge_style, dict):
            issues.append(issue("error", "edge.style", "edge style must be an object", eid))
        elif isinstance(custom_edge_style, dict):
            for field in sorted(set(custom_edge_style) - EDGE_STYLE_FIELDS):
                issues.append(issue(
                    "warning", "edge.style.unknown-field",
                    f"unknown edge style field: {field}", eid,
                ))
            cardinalities = [
                custom_edge_style.get("start_cardinality"),
                custom_edge_style.get("end_cardinality"),
            ]
            for cardinality in cardinalities:
                if cardinality is not None and cardinality not in ALLOWED_CARDINALITIES:
                    issues.append(issue(
                        "error", "edge.cardinality",
                        f"unknown cardinality: {cardinality}", eid,
                    ))
            if any(cardinality is not None for cardinality in cardinalities) and not all(
                cardinality in ALLOWED_CARDINALITIES for cardinality in cardinalities
            ):
                issues.append(issue(
                    "error", "edge.cardinality",
                    "ER relationships require both endpoint cardinalities", eid,
                ))
            for field in ("source_port", "target_port"):
                port = custom_edge_style.get(field)
                if port is not None and port not in ALLOWED_PORTS:
                    issues.append(issue(
                        "error", "edge.port",
                        f"{field} must be auto, north, east, south, or west", eid,
                    ))
            for field in ("source_offset", "target_offset"):
                offset = custom_edge_style.get(field)
                if offset is not None and (
                    not isinstance(offset, (int, float))
                    or isinstance(offset, bool)
                    or not 0 <= offset <= 1
                ):
                    issues.append(issue(
                        "error", "edge.port-offset",
                        f"{field} must be a number from 0 to 1", eid,
                    ))
        degrees[source] += 1
        degrees[target] += 1

    node_kinds = {
        str(node["id"]): str(node.get("kind", "service"))
        for node in nodes if isinstance(node, dict) and node.get("id")
    }
    for nid in sorted(node_ids):
        if degrees[nid] == 0 and len(node_ids) > 1 and node_kinds.get(nid) != "note":
            issues.append(issue("warning", "node.isolated", "node has no relationships", nid))
    return issues


def stable_ranks(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    ids = [str(node["id"]) for node in nodes]
    adjacency: dict[str, list[str]] = {nid: [] for nid in ids}
    indegree = {nid: 0 for nid in ids}
    for edge in edges:
        source, target = str(edge["from"]), str(edge["to"])
        if source in adjacency and target in indegree and target not in adjacency[source]:
            adjacency[source].append(target)
            indegree[target] += 1
    queue = deque(sorted(nid for nid, degree in indegree.items() if degree == 0))
    ranks = {nid: 0 for nid in ids}
    visited: set[str] = set()
    while queue:
        source = queue.popleft()
        visited.add(source)
        for target in sorted(adjacency[source]):
            ranks[target] = max(ranks[target], ranks[source] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    # Place cycle members deterministically after their strongest predecessor.
    for nid in sorted(set(ids) - visited):
        predecessors = [str(e["from"]) for e in edges if str(e["to"]) == nid and str(e["from"]) != nid]
        ranks[nid] = max((ranks.get(pred, 0) + 1 for pred in predecessors), default=0)
    return ranks


def entity_field_type(field: dict[str, Any]) -> str:
    value = str(field.get("type", ""))
    if not field.get("nullable", True):
        value += " NOT NULL"
    if "default" in field:
        default = str(field["default"]).lower() if isinstance(field["default"], bool) else str(field["default"])
        value += f" DEFAULT {default}"
    return value


def node_size(node: dict[str, Any]) -> tuple[int, int]:
    explicit = node.get("size", {})
    if isinstance(explicit, dict) and explicit:
        return int(explicit.get("width", 180)), int(explicit.get("height", 72))
    if node.get("kind") == "entity":
        fields = node.get("fields", []) if isinstance(node.get("fields"), list) else []
        longest = max(
            [
                len(str(node.get("label", ""))),
                *[
                    len(str(field.get("name", ""))) + len(entity_field_type(field)) + 10
                    for field in fields if isinstance(field, dict)
                ],
            ],
            default=20,
        )
        return max(280, min(440, 80 + longest * 7)), 48 + len(fields) * 28
    label = str(node.get("label", ""))
    description = str(node.get("description", ""))
    width = max(150, min(280, 56 + max(len(label), min(len(description), 30)) * 7))
    height = 72 if description else 56
    if node.get("kind") == "decision":
        return max(width, 150), max(height, 90)
    return width, height


def calculate_layout(data: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    direction = data.get("diagram", {}).get("direction", "LR")
    gap = int(data.get("diagram", {}).get("gap", 100))
    ranks = stable_ranks(nodes, edges)
    rank_nodes: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        rank_nodes[ranks[str(node["id"])]].append(node)
    ordered_groups = [str(group["id"]) for group in data.get("groups", [])]
    if any(not node.get("group") for node in nodes):
        ordered_groups.insert(0, "__ungrouped__")
    for node in nodes:
        group_id = str(node.get("group") or "__ungrouped__")
        if group_id not in ordered_groups:
            ordered_groups.append(group_id)

    primary_origins: dict[int, int] = {}
    primary_cursor = 100
    for rank in sorted(rank_nodes):
        primary_origins[rank] = primary_cursor
        max_primary = max(
            (node_size(node)[0 if direction == "LR" else 1] for node in rank_nodes[rank]),
            default=160,
        )
        primary_cursor += max_primary + gap + 60

    band_origins: dict[str, int] = {}
    band_cursor = 100
    for group_id in ordered_groups:
        max_cross_total = 0
        for rank in rank_nodes:
            members = [
                node for node in rank_nodes[rank]
                if str(node.get("group") or "__ungrouped__") == group_id
            ]
            if not members:
                continue
            sizes = [node_size(node)[1 if direction == "LR" else 0] for node in members]
            max_cross_total = max(max_cross_total, sum(sizes) + gap * max(0, len(sizes) - 1))
        if max_cross_total:
            band_origins[group_id] = band_cursor
            band_cursor += max_cross_total + gap + 50

    layout: dict[str, tuple[int, int, int, int]] = {}
    for rank in sorted(rank_nodes):
        by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in rank_nodes[rank]:
            by_group[str(node.get("group") or "__ungrouped__")].append(node)
        for members in by_group.values():
            members.sort(key=lambda item: str(item["id"]))
        for group_id in ordered_groups:
            cross_cursor = band_origins.get(group_id, 100)
            for node in by_group.get(group_id, []):
                width, height = node_size(node)
                position = node.get("position")
                if isinstance(position, dict) and "x" in position and "y" in position:
                    x, y = int(position["x"]), int(position["y"])
                elif direction == "LR":
                    x, y = primary_origins[rank], cross_cursor
                else:
                    x, y = cross_cursor, primary_origins[rank]
                layout[str(node["id"])] = (x, y, width, height)
                cross_cursor += (height if direction == "LR" else width) + gap
    return layout


def edge_semantic_key(edge: dict[str, Any], index: int) -> str:
    return str(edge.get("id") or f"{edge.get('from', '')}-to-{edge.get('to', '')}-{index + 1}")


def default_port_sides(
    source: tuple[int, int, int, int],
    target: tuple[int, int, int, int],
    direction: str,
) -> tuple[str, str]:
    source_center = (source[0] + source[2] / 2, source[1] + source[3] / 2)
    target_center = (target[0] + target[2] / 2, target[1] + target[3] / 2)
    delta_x = target_center[0] - source_center[0]
    delta_y = target_center[1] - source_center[1]
    if direction == "LR" and abs(delta_x) >= abs(delta_y) * 0.35:
        return ("east", "west") if delta_x >= 0 else ("west", "east")
    if direction == "TB" and abs(delta_y) >= abs(delta_x) * 0.35:
        return ("south", "north") if delta_y >= 0 else ("north", "south")
    if abs(delta_x) >= abs(delta_y):
        return ("east", "west") if delta_x >= 0 else ("west", "east")
    return ("south", "north") if delta_y >= 0 else ("north", "south")


def port_coordinates(side: str, offset: float) -> tuple[float, float]:
    if side == "north":
        return offset, 0
    if side == "east":
        return 1, offset
    if side == "south":
        return offset, 1
    return 0, offset


def port_point(
    box: tuple[int, int, int, int], side: str, offset: float,
) -> tuple[float, float]:
    x, y, width, height = box
    relative_x, relative_y = port_coordinates(side, offset)
    return x + width * relative_x, y + height * relative_y


def offset_point(point: tuple[float, float], side: str, distance: float) -> tuple[float, float]:
    delta = {
        "north": (0, -distance),
        "east": (distance, 0),
        "south": (0, distance),
        "west": (-distance, 0),
    }[side]
    return point[0] + delta[0], point[1] + delta[1]


def simplify_route(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for point in points:
        if result and point == result[-1]:
            continue
        if len(result) >= 2:
            first, second = result[-2], result[-1]
            if (
                (first[0] == second[0] == point[0])
                or (first[1] == second[1] == point[1])
            ):
                result[-1] = point
                continue
        result.append(point)
    return result


def route_segments(
    points: list[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [
        (points[index], points[index + 1])
        for index in range(len(points) - 1)
        if points[index] != points[index + 1]
    ]


def segment_bounds(
    start: tuple[float, float], end: tuple[float, float],
) -> tuple[float, float, float, float]:
    return (
        min(start[0], end[0]), min(start[1], end[1]),
        max(start[0], end[0]), max(start[1], end[1]),
    )


def bounds_intersect(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] < right[0] or right[2] < left[0]
        or left[3] < right[1] or right[3] < left[1]
    )


def route_bounds(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[float, float, float, float]:
    if not segments:
        return 0, 0, 0, 0
    bounds = [segment_bounds(start, end) for start, end in segments]
    return (
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    )


def orthogonal_candidates(
    start: tuple[float, float],
    end: tuple[float, float],
    source_side: str,
    target_side: str,
    obstacles: list[tuple[str, float, float, float, float]] | None = None,
) -> list[list[tuple[float, float]]]:
    source_stub = offset_point(start, source_side, 28)
    target_stub = offset_point(end, target_side, 28)
    min_x, max_x = sorted((source_stub[0], target_stub[0]))
    min_y, max_y = sorted((source_stub[1], target_stub[1]))
    x_mid = (source_stub[0] + target_stub[0]) / 2
    y_mid = (source_stub[1] + target_stub[1]) / 2
    x_corridors = [x_mid, x_mid - 36, x_mid + 36, min_x - 48, max_x + 48]
    y_corridors = [y_mid, y_mid - 36, y_mid + 36, min_y - 48, max_y + 48]
    nearby_obstacles = sorted(
        obstacles or [],
        key=lambda box: (
            abs((box[1] + box[3] / 2) - x_mid)
            + abs((box[2] + box[4] / 2) - y_mid),
            box[0],
        ),
    )[:12]
    for _, x, y, width, height in nearby_obstacles:
        x_corridors.extend((x - 36, x + width + 36))
        y_corridors.extend((y - 36, y + height + 36))
    candidates: list[list[tuple[float, float]]] = []
    if source_stub[0] == target_stub[0] or source_stub[1] == target_stub[1]:
        candidates.append([start, source_stub, target_stub, end])
    for corridor in x_corridors:
        candidates.append([
            start, source_stub, (corridor, source_stub[1]),
            (corridor, target_stub[1]), target_stub, end,
        ])
    for corridor in y_corridors:
        candidates.append([
            start, source_stub, (source_stub[0], corridor),
            (target_stub[0], corridor), target_stub, end,
        ])
    unique: list[list[tuple[float, float]]] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for candidate in candidates:
        simplified = simplify_route(candidate)
        key = tuple(simplified)
        if key not in seen:
            seen.add(key)
            unique.append(simplified)
    return unique


def route_score(
    points: list[tuple[float, float]],
    boxes: list[tuple[str, float, float, float, float]],
    excluded_nodes: set[str],
    previous: list[dict[str, Any]],
    endpoint_nodes: set[str],
    preference: int,
) -> tuple[int, int, int, float, int]:
    segments = route_segments(points)
    segment_boxes = [
        (start, end, segment_bounds(start, end)) for start, end in segments
    ]
    node_hits = sum(
        1
        for start, end, bounds in segment_boxes
        for box in boxes
        if (
            box[0] not in excluded_nodes
            and bounds_intersect(
                bounds, (box[1], box[2], box[1] + box[3], box[2] + box[4])
            )
            and segment_crosses_rectangle(start, end, box)
        )
    )
    crossings = 0
    candidate_bounds = route_bounds(segments)
    for prior in previous:
        if (
            endpoint_nodes & prior["nodes"]
            or not bounds_intersect(candidate_bounds, prior["bounds"])
        ):
            continue
        crossings += sum(
            1
            for start, end, bounds in segment_boxes
            for other_start, other_end, other_bounds in prior["segment_boxes"]
            if (
                bounds_intersect(bounds, other_bounds)
                and segments_cross(start, end, other_start, other_end)
            )
        )
    length = sum(
        abs(end[0] - start[0]) + abs(end[1] - start[1])
        for start, end in segments
    )
    return node_hits, crossings, max(0, len(segments) - 1), length, preference


def edge_route_plans(
    data: dict[str, Any],
    layout: dict[str, tuple[int, int, int, int]] | None = None,
) -> list[dict[str, Any]]:
    layout = layout or calculate_layout(data)
    edges = data.get("edges", [])
    direction = str(data.get("diagram", {}).get("direction", "LR"))
    endpoint_specs: dict[tuple[int, str], tuple[str, float | None]] = {}
    assignments: dict[tuple[str, str], list[tuple[str, int, str]]] = defaultdict(list)
    for index, edge in enumerate(edges):
        source_id, target_id = str(edge["from"]), str(edge["to"])
        custom = edge.get("style", {}) if isinstance(edge.get("style"), dict) else {}
        if source_id == target_id:
            defaults = ("east", "north")
        else:
            defaults = default_port_sides(layout[source_id], layout[target_id], direction)
        source_side = str(custom.get("source_port", "auto"))
        target_side = str(custom.get("target_port", "auto"))
        source_side = defaults[0] if source_side == "auto" else source_side
        target_side = defaults[1] if target_side == "auto" else target_side
        source_offset = custom.get("source_offset")
        target_offset = custom.get("target_offset")
        endpoint_specs[(index, "source")] = (
            source_side, float(source_offset) if source_offset is not None else None,
        )
        endpoint_specs[(index, "target")] = (
            target_side, float(target_offset) if target_offset is not None else None,
        )
        key = edge_semantic_key(edge, index)
        assignments[(source_id, source_side)].append((key, index, "source"))
        assignments[(target_id, target_side)].append((key, index, "target"))
    endpoint_offsets: dict[tuple[int, str], float] = {}
    for endpoints in assignments.values():
        ordered = sorted(endpoints)
        count = len(ordered)
        for position, (_, index, role) in enumerate(ordered):
            _, explicit = endpoint_specs[(index, role)]
            endpoint_offsets[(index, role)] = (
                explicit if explicit is not None
                else 0.5 if count == 1
                else 0.18 + 0.64 * position / (count - 1)
            )

    boxes = [
        (node_id, float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        for node_id, box in layout.items()
    ]
    plans: list[dict[str, Any] | None] = [None] * len(edges)
    previous: list[dict[str, Any]] = []
    ordered_edges = sorted(
        enumerate(edges), key=lambda item: edge_semantic_key(item[1], item[0]),
    )
    for index, edge in ordered_edges:
        source_id, target_id = str(edge["from"]), str(edge["to"])
        source_side = endpoint_specs[(index, "source")][0]
        target_side = endpoint_specs[(index, "target")][0]
        source_offset = endpoint_offsets[(index, "source")]
        target_offset = endpoint_offsets[(index, "target")]
        start = port_point(layout[source_id], source_side, source_offset)
        end = port_point(layout[target_id], target_side, target_offset)
        if source_id == target_id:
            x, y, width, _ = layout[source_id]
            points = simplify_route([
                start, (x + width + 70, start[1]), (x + width + 70, y - 50),
                (end[0], y - 50), end,
            ])
        else:
            candidates = orthogonal_candidates(
                start, end, source_side, target_side,
                [box for box in boxes if box[0] not in {source_id, target_id}],
            )
            scored = [
                (
                    route_score(
                        candidate, boxes, {source_id, target_id}, previous,
                        {source_id, target_id}, preference,
                    ),
                    candidate,
                )
                for preference, candidate in enumerate(candidates)
            ]
            points = min(scored, key=lambda item: item[0])[1]
        source_xy = port_coordinates(source_side, source_offset)
        target_xy = port_coordinates(target_side, target_offset)
        plan = {
            "source_port": source_side,
            "target_port": target_side,
            "source_offset": source_offset,
            "target_offset": target_offset,
            "source_xy": source_xy,
            "target_xy": target_xy,
            "points": points,
        }
        plans[index] = plan
        segments = route_segments(points)
        previous.append({
            "nodes": {source_id, target_id},
            "segments": segments,
            "segment_boxes": [
                (start, end, segment_bounds(start, end))
                for start, end in segments
            ],
            "bounds": route_bounds(segments),
        })
    return [plan for plan in plans if plan is not None]


def route_label_position(points: list[tuple[float, float]]) -> tuple[float, float]:
    segments = route_segments(points)
    if not segments:
        return points[0]
    start, end = max(
        segments,
        key=lambda segment: (
            abs(segment[1][0] - segment[0][0])
            + abs(segment[1][1] - segment[0][1])
        ),
    )
    return (start[0] + end[0]) / 2, (start[1] + end[1]) / 2 - 8


def style_string(parts: dict[str, Any]) -> str:
    return ";".join(f"{key}={str(value).lower() if isinstance(value, bool) else value}" for key, value in parts.items()) + ";"


def encode_ir_metadata(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def node_style(node: dict[str, Any], theme: dict[str, Any]) -> str:
    kind = str(node.get("kind", "service"))
    fill, stroke = theme.get(kind, theme["service"])
    custom = node.get("style", {}) if isinstance(node.get("style"), dict) else {}
    fill, stroke = custom.get("fill", fill), custom.get("stroke", stroke)
    parts: dict[str, Any] = {
        "whiteSpace": "wrap", "html": 1, "rounded": 1, "arcSize": 12,
        "fillColor": fill, "strokeColor": stroke, "strokeWidth": 2,
        "fontColor": custom.get("font", theme["font"]), "fontSize": 13,
        "align": "center", "verticalAlign": "middle", "spacing": 8,
    }
    shapes = load_shape_registry()["shapes"]
    registry_entry = shapes.get(kind, shapes["service"])
    parts.update(registry_entry["style"])
    if kind == "entity":
        parts.update({
            "rounded": 0, "align": "left", "verticalAlign": "top",
            "spacing": 0, "overflow": "fill",
        })
    if "dashed" in custom:
        parts["dashed"] = 1 if custom["dashed"] else 0
    if "rounded" in custom:
        parts["rounded"] = 1 if custom["rounded"] else 0
    return style_string(parts)


def edge_style(
    edge: dict[str, Any],
    theme: dict[str, Any],
    direction: str,
    route_plan: dict[str, Any] | None = None,
) -> str:
    kind = edge.get("kind", "sync")
    custom = edge.get("style", {}) if isinstance(edge.get("style"), dict) else {}
    parts: dict[str, Any] = {
        "edgeStyle": "orthogonalEdgeStyle", "rounded": 1, "orthogonalLoop": 1,
        "jettySize": "auto", "html": 1, "strokeColor": custom.get("color", theme["edge"]),
        "strokeWidth": custom.get("width", 2), "endArrow": "block", "endFill": 1,
        "fontColor": theme["font"], "fontSize": 11, "labelBackgroundColor": theme["background"],
    }
    if route_plan:
        source_x, source_y = route_plan["source_xy"]
        target_x, target_y = route_plan["target_xy"]
        parts.update({
            "exitX": round(source_x, 4), "exitY": round(source_y, 4),
            "entryX": round(target_x, 4), "entryY": round(target_y, 4),
            "exitDx": 0, "exitDy": 0, "entryDx": 0, "entryDy": 0,
            "exitPerimeter": 0, "entryPerimeter": 0,
        })
    elif direction == "LR":
        parts.update({"exitX": 1, "exitY": 0.5, "entryX": 0, "entryY": 0.5})
    else:
        parts.update({"exitX": 0.5, "exitY": 1, "entryX": 0.5, "entryY": 0})
    if kind in {"async", "dependency"}:
        parts["dashed"] = 1
    if kind == "async":
        parts["endArrow"] = "open"
        parts["endFill"] = 0
    if kind == "association":
        parts["endArrow"] = "none"
    start_cardinality = custom.get("start_cardinality")
    end_cardinality = custom.get("end_cardinality")
    if start_cardinality in CARDINALITY_MARKERS or end_cardinality in CARDINALITY_MARKERS:
        parts.update({
            "edgeStyle": "entityRelationEdgeStyle",
            "rounded": 0,
            "startArrow": CARDINALITY_MARKERS.get(str(start_cardinality), "none"),
            "endArrow": CARDINALITY_MARKERS.get(str(end_cardinality), "none"),
            "startFill": 0,
            "endFill": 0,
        })
    if custom.get("dashed") is not None:
        parts["dashed"] = 1 if custom["dashed"] else 0
    return style_string(parts)


def entity_field_markers(field: dict[str, Any]) -> str:
    markers = []
    if field.get("primary_key"):
        markers.append("PK")
    if field.get("foreign_key"):
        markers.append("FK")
    if field.get("unique"):
        markers.append("UK")
    return " ".join(markers) or "·"


def node_value(node: dict[str, Any], theme: dict[str, Any]) -> str:
    if node.get("kind") != "entity":
        value = f"<b>{html.escape(str(node['label']))}</b>"
        description = str(node.get("description", "")).strip()
        if description:
            value += (
                "<br><font style=\"font-size:10px\">"
                f"{html.escape(description)}</font>"
            )
        return value
    rows = []
    for field in node.get("fields", []):
        if not isinstance(field, dict):
            continue
        rows.append(
            "<tr>"
            f"<td style=\"padding:5px 7px;color:{theme['edge']};font-size:10px;\">"
            f"{html.escape(entity_field_markers(field))}</td>"
            f"<td style=\"padding:5px 7px;\"><b>{html.escape(str(field['name']))}</b></td>"
            f"<td style=\"padding:5px 7px;text-align:right;color:{theme['edge']};\">"
            f"{html.escape(entity_field_type(field))}</td>"
            "</tr>"
        )
    return (
        "<table style=\"width:100%;height:100%;border-collapse:collapse;\">"
        f"<tr><td colspan=\"3\" style=\"padding:9px;background:{theme['group_fill']};"
        f"font-weight:bold;font-size:14px;\">{html.escape(str(node['label']))}</td></tr>"
        + "".join(rows)
        + "</table>"
    )


def page_documents(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if "pages" not in data:
        return [("main", data)]
    defaults = data.get("diagram", {}) if isinstance(data.get("diagram"), dict) else {}
    documents = []
    for page in data.get("pages", []):
        page_diagram = page.get("diagram", {}) if isinstance(page.get("diagram"), dict) else {}
        documents.append((
            str(page["id"]),
            {
                "version": "1",
                "diagram": {**defaults, **page_diagram, "title": page["title"]},
                "groups": page.get("groups", []),
                "nodes": page.get("nodes", []),
                "edges": page.get("edges", []),
            },
        ))
    return documents


def append_page(mxfile: ET.Element, page_id: str, data: dict[str, Any]) -> None:
    diagram_data = data.get("diagram", {})
    title = str(diagram_data.get("title", "Diagram"))
    direction = str(diagram_data.get("direction", "LR"))
    theme = resolve_theme(diagram_data)
    layout = calculate_layout(data)
    route_plans = edge_route_plans(data, layout)

    diagram = ET.SubElement(mxfile, "diagram", {
        "id": f"page-{page_id}",
        "name": title,
        "data-ir-page": encode_ir_metadata({
            "id": page_id,
            "diagram": diagram_data,
        }),
    })
    model = ET.SubElement(diagram, "mxGraphModel", {
        "dx": "1200", "dy": "800", "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": "1169", "pageHeight": "827",
        "background": str(diagram_data.get("background", theme["background"])),
        "math": "0", "shadow": "0",
    })
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    groups = data.get("groups", [])
    for group in groups:
        member_boxes = [layout[str(n["id"])] for n in data.get("nodes", []) if n.get("group") == group["id"]]
        if not member_boxes:
            continue
        min_x = min(box[0] for box in member_boxes) - 30
        min_y = min(box[1] for box in member_boxes) - 55
        max_x = max(box[0] + box[2] for box in member_boxes) + 30
        max_y = max(box[1] + box[3] for box in member_boxes) + 30
        cell = ET.SubElement(root, "mxCell", {
            "id": f"group-{group['id']}", "value": str(group["label"]), "vertex": "1", "parent": "1",
            "data-ir": encode_ir_metadata(group),
            "style": style_string({
                "swimlane": 1, "horizontal": 1, "startSize": 30, "rounded": 1,
                "fillColor": theme["group_fill"], "swimlaneFillColor": theme["group_fill"],
                "strokeColor": theme["group_stroke"], "fontColor": theme["font"],
                "fontStyle": 1, "html": 1, "collapsible": 0,
            }),
        })
        ET.SubElement(cell, "mxGeometry", {
            "x": str(min_x), "y": str(min_y), "width": str(max_x - min_x),
            "height": str(max_y - min_y), "as": "geometry",
        })

    for node in data.get("nodes", []):
        nid = str(node["id"])
        x, y, width, height = layout[nid]
        value = node_value(node, theme)
        style = node_style(node, theme)
        cell = ET.SubElement(root, "mxCell", {
            "id": f"node-{nid}", "value": value,
            "vertex": "1", "parent": "1",
            "data-ir": encode_ir_metadata(node),
            "data-ir-value": value,
            "data-ir-style": style,
            "style": style,
        })
        if node.get("link"):
            cell.set("link", f"data:page/id,page-{node['link']}")
        ET.SubElement(cell, "mxGeometry", {
            "x": str(x), "y": str(y), "width": str(width), "height": str(height), "as": "geometry",
        })

    edge_counts: dict[str, int] = defaultdict(int)
    for index, edge in enumerate(data.get("edges", []), start=1):
        route_plan = route_plans[index - 1]
        source, target = str(edge["from"]), str(edge["to"])
        base_id = str(edge.get("id", f"{source}-to-{target}"))
        edge_counts[base_id] += 1
        eid = base_id if edge_counts[base_id] == 1 else f"{base_id}-{edge_counts[base_id]}"
        edge_metadata = copy.deepcopy(edge)
        edge_metadata["id"] = eid
        style = edge_style(edge, theme, direction, route_plan)
        cell = ET.SubElement(root, "mxCell", {
            "id": f"edge-{eid}", "value": str(edge.get("label", "")), "edge": "1", "parent": "1",
            "source": f"node-{source}", "target": f"node-{target}",
            "data-ir": encode_ir_metadata(edge_metadata),
            "data-ir-style": style,
            "style": style,
        })
        geometry = ET.SubElement(
            cell, "mxGeometry", {"relative": "1", "as": "geometry"},
        )
        internal_points = route_plan["points"][1:-1]
        if internal_points:
            point_array = ET.SubElement(geometry, "Array", {"as": "points"})
            for x, y in internal_points:
                ET.SubElement(point_array, "mxPoint", {
                    "x": str(round(x, 3)), "y": str(round(y, 3)),
                })


def compile_drawio(data: dict[str, Any]) -> ET.ElementTree:
    mxfile = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "agent": "drawio-diagram-engineer",
            "version": VERSION,
            "data-ir-version": IR_METADATA_VERSION,
        },
    )
    for page_id, page_data in page_documents(data):
        append_page(mxfile, page_id, page_data)
    ET.indent(mxfile, space="  ")
    return ET.ElementTree(mxfile)


def select_page(data: dict[str, Any], page_id: str | None = None) -> dict[str, Any]:
    documents = page_documents(data)
    if page_id:
        for candidate_id, page in documents:
            if candidate_id == page_id:
                return page
        raise ValueError(f"unknown page: {page_id}")
    if len(documents) > 1:
        raise ValueError("multi-page IR requires --page for SVG preview")
    return documents[0][1]


def compile_svg(data: dict[str, Any]) -> ET.ElementTree:
    """Create a dependency-free review preview from a single-page IR."""
    diagram = data.get("diagram", {})
    direction = str(diagram.get("direction", "LR"))
    theme = resolve_theme(diagram)
    layout = calculate_layout(data)
    route_plans = edge_route_plans(data, layout)
    group_boxes: list[tuple[dict[str, Any], int, int, int, int]] = []
    for group in data.get("groups", []):
        members = [layout[str(node["id"])] for node in data.get("nodes", []) if node.get("group") == group["id"]]
        if not members:
            continue
        min_x = min(box[0] for box in members) - 30
        min_y = min(box[1] for box in members) - 55
        max_x = max(box[0] + box[2] for box in members) + 30
        max_y = max(box[1] + box[3] for box in members) + 30
        group_boxes.append((group, min_x, min_y, max_x - min_x, max_y - min_y))
    max_x = max(
        [x + width for x, _, width, _ in layout.values()]
        + [x + width for _, x, _, width, _ in group_boxes]
        + [800]
    ) + 80
    max_y = max(
        [y + height for _, y, _, height in layout.values()]
        + [y + height for _, _, y, _, height in group_boxes]
        + [500]
    ) + 80
    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "width": str(max_x), "height": str(max_y),
        "viewBox": f"0 0 {max_x} {max_y}", "role": "img",
        "aria-label": str(diagram.get("title", "Diagram preview")),
    })
    ET.SubElement(svg, "rect", {
        "width": "100%", "height": "100%",
        "fill": str(diagram.get("background", theme["background"])),
    })
    defs = ET.SubElement(svg, "defs")
    edge_colors = {
        str(
            edge.get("style", {}).get("color", theme["edge"])
            if isinstance(edge.get("style"), dict) else theme["edge"]
        )
        for edge in data.get("edges", [])
        if isinstance(edge, dict)
    } | {str(theme["edge"])}
    marker_ids: dict[str, str] = {}
    for color in sorted(edge_colors):
        marker_id = f"arrow-{slugify(color)}"
        marker_ids[color] = marker_id
        marker = ET.SubElement(defs, "marker", {
            "id": marker_id, "viewBox": "0 0 10 10", "refX": "9", "refY": "5",
            "markerWidth": "7", "markerHeight": "7", "orient": "auto-start-reverse",
        })
        ET.SubElement(marker, "path", {
            "d": "M 0 0 L 10 5 L 0 10 z", "fill": color,
        })

    for group, x, y, width, height in group_boxes:
        ET.SubElement(svg, "rect", {
            "x": str(x), "y": str(y), "width": str(width), "height": str(height),
            "rx": "14", "fill": theme["group_fill"], "stroke": theme["group_stroke"],
            "stroke-width": "2",
        })
        label = ET.SubElement(svg, "text", {
            "x": str(x + 16), "y": str(y + 24), "fill": theme["font"],
            "font-family": "Inter, Arial, sans-serif", "font-size": "14", "font-weight": "700",
        })
        label.text = str(group["label"])

    node_map = {str(node["id"]): node for node in data.get("nodes", [])}
    for edge_index, edge in enumerate(data.get("edges", [])):
        source_id, target_id = str(edge["from"]), str(edge["to"])
        route_plan = route_plans[edge_index]
        points = route_plan["points"]
        start, end = points[0], points[-1]
        edge_kind = str(edge.get("kind", "sync"))
        edge_custom = edge.get("style", {}) if isinstance(edge.get("style"), dict) else {}
        edge_color = str(edge_custom.get("color", theme["edge"]))
        attrs = {
            "points": " ".join(f"{x},{y}" for x, y in points), "fill": "none",
            "stroke": edge_color,
            "stroke-width": str(edge_custom.get("width", 2)),
            "marker-end": f"url(#{marker_ids[edge_color]})",
        }
        if edge_kind in {"async", "dependency"} or edge_custom.get("dashed"):
            attrs["stroke-dasharray"] = "7 5"
        if edge_kind == "association":
            attrs.pop("marker-end")
        if (
            edge_custom.get("start_cardinality") in CARDINALITY_LABELS
            or edge_custom.get("end_cardinality") in CARDINALITY_LABELS
        ):
            attrs.pop("marker-end", None)
        ET.SubElement(svg, "polyline", attrs)
        edge_label = str(edge.get("label", "")).strip()
        if edge_label:
            label_x, label_y = route_label_position(points)
            label = ET.SubElement(svg, "text", {
                "x": str(label_x), "y": str(label_y),
                "fill": theme["font"], "font-family": "Inter, Arial, sans-serif",
                "font-size": "11", "text-anchor": "middle",
            })
            label.text = edge_label
        if edge_custom.get("start_cardinality") in CARDINALITY_LABELS:
            cardinality = ET.SubElement(svg, "text", {
                "x": str(start[0] + (18 if direction == "LR" else 12)),
                "y": str(start[1] - (8 if direction == "LR" else -18)),
                "fill": theme["font"], "font-family": "Inter, Arial, sans-serif",
                "font-size": "11", "font-weight": "700",
            })
            cardinality.text = CARDINALITY_LABELS[str(edge_custom["start_cardinality"])]
        if edge_custom.get("end_cardinality") in CARDINALITY_LABELS:
            cardinality = ET.SubElement(svg, "text", {
                "x": str(end[0] - (34 if direction == "LR" else -12)),
                "y": str(end[1] - (8 if direction == "LR" else 10)),
                "fill": theme["font"], "font-family": "Inter, Arial, sans-serif",
                "font-size": "11", "font-weight": "700",
            })
            cardinality.text = CARDINALITY_LABELS[str(edge_custom["end_cardinality"])]

    for node_id, node in node_map.items():
        x, y, width, height = layout[node_id]
        kind = str(node.get("kind", "service"))
        fill, stroke = theme.get(kind, theme["service"])
        custom = node.get("style", {}) if isinstance(node.get("style"), dict) else {}
        fill, stroke = custom.get("fill", fill), custom.get("stroke", stroke)
        if kind == "entity":
            ET.SubElement(svg, "rect", {
                "x": str(x), "y": str(y), "width": str(width), "height": str(height),
                "rx": "0", "fill": fill, "stroke": stroke, "stroke-width": "2",
            })
            ET.SubElement(svg, "rect", {
                "x": str(x), "y": str(y), "width": str(width), "height": "48",
                "fill": theme["group_fill"], "stroke": stroke, "stroke-width": "2",
            })
            header = ET.SubElement(svg, "text", {
                "x": str(x + 12), "y": str(y + 30), "fill": theme["font"],
                "font-family": "Inter, Arial, sans-serif", "font-size": "14",
                "font-weight": "700",
            })
            header.text = str(node["label"])
            for field_index, field in enumerate(node.get("fields", [])):
                if not isinstance(field, dict):
                    continue
                row_y = y + 48 + field_index * 28
                if field_index:
                    ET.SubElement(svg, "line", {
                        "x1": str(x), "x2": str(x + width), "y1": str(row_y),
                        "y2": str(row_y), "stroke": theme["group_stroke"],
                        "stroke-width": "1", "opacity": "0.45",
                    })
                marker_text = ET.SubElement(svg, "text", {
                    "x": str(x + 8), "y": str(row_y + 19), "fill": theme["edge"],
                    "font-family": "Inter, Arial, sans-serif", "font-size": "9",
                    "font-weight": "700",
                })
                marker_text.text = entity_field_markers(field)
                name_text = ET.SubElement(svg, "text", {
                    "x": str(x + 52), "y": str(row_y + 19), "fill": theme["font"],
                    "font-family": "Inter, Arial, sans-serif", "font-size": "11",
                    "font-weight": "700" if field.get("primary_key") else "400",
                })
                name_text.text = str(field.get("name", ""))
                type_text = ET.SubElement(svg, "text", {
                    "x": str(x + width - 8), "y": str(row_y + 19),
                    "fill": theme["edge"], "font-family": "Inter, Arial, sans-serif",
                    "font-size": "10", "text-anchor": "end",
                })
                type_text.text = entity_field_type(field)
            continue
        if kind == "decision":
            points = f"{x + width / 2},{y} {x + width},{y + height / 2} {x + width / 2},{y + height} {x},{y + height / 2}"
            ET.SubElement(svg, "polygon", {
                "points": points, "fill": fill, "stroke": stroke, "stroke-width": "2",
            })
        else:
            ET.SubElement(svg, "rect", {
                "x": str(x), "y": str(y), "width": str(width), "height": str(height),
                "rx": "12", "fill": fill, "stroke": stroke, "stroke-width": "2",
                **(
                    {"stroke-dasharray": "7 5"}
                    if kind == "external" or custom.get("dashed") else {}
                ),
            })
            if kind == "database":
                ET.SubElement(svg, "ellipse", {
                    "cx": str(x + width / 2), "cy": str(y + 10), "rx": str(width / 2),
                    "ry": "10", "fill": fill, "stroke": stroke, "stroke-width": "2",
                })
        label = ET.SubElement(svg, "text", {
            "x": str(x + width / 2), "y": str(y + height / 2 - (7 if node.get("description") else 0)),
            "fill": custom.get("font", theme["font"]), "font-family": "Inter, Arial, sans-serif",
            "font-size": "13", "font-weight": "700", "text-anchor": "middle",
        })
        label.text = str(node["label"])
        if node.get("description"):
            description = ET.SubElement(svg, "text", {
                "x": str(x + width / 2), "y": str(y + height / 2 + 13),
                "fill": custom.get("font", theme["font"]), "font-family": "Inter, Arial, sans-serif",
                "font-size": "10", "text-anchor": "middle",
            })
            text = str(node["description"])
            description.text = text if len(text) <= 42 else text[:39] + "…"
    ET.indent(svg, space="  ")
    return ET.ElementTree(svg)


def parse_number(value: str | None, default: float = 0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def load_drawio_root(path: Path) -> ET.Element:
    """Load uncompressed or standard compressed draw.io XML."""
    raw_xml = path.read_bytes()
    if len(raw_xml) > MAX_XML_INPUT_BYTES:
        raise ValueError(
            f"draw.io input exceeds {MAX_XML_INPUT_BYTES // (1024 * 1024)} MiB safety limit"
        )
    upper_xml = raw_xml.upper()
    if b"<!DOCTYPE" in upper_xml or b"<!ENTITY" in upper_xml:
        raise ValueError("draw.io input contains a prohibited DTD or entity declaration")
    root = ET.fromstring(raw_xml)
    if root.findall(".//mxCell"):
        return root
    decoded_models: list[ET.Element] = []
    for diagram in root.findall(".//diagram"):
        payload = (diagram.text or "").strip()
        if not payload:
            continue
        try:
            compressed = base64.b64decode(payload, validate=True)
            decompressor = zlib.decompressobj(-15)
            decoded = decompressor.decompress(compressed, MAX_DECOMPRESSED_PAGE_BYTES + 1)
            if len(decoded) > MAX_DECOMPRESSED_PAGE_BYTES or decompressor.unconsumed_tail:
                raise ValueError(
                    "decompressed page exceeds "
                    f"{MAX_DECOMPRESSED_PAGE_BYTES // (1024 * 1024)} MiB safety limit"
                )
            decoded += decompressor.flush()
            if len(decoded) > MAX_DECOMPRESSED_PAGE_BYTES:
                raise ValueError(
                    "decompressed page exceeds "
                    f"{MAX_DECOMPRESSED_PAGE_BYTES // (1024 * 1024)} MiB safety limit"
                )
            xml_text = urllib.parse.unquote(decoded.decode("utf-8"))
            decoded_models.append(ET.fromstring(xml_text))
        except (ValueError, zlib.error, UnicodeDecodeError, ET.ParseError) as exc:
            raise ValueError(f"cannot decode compressed draw.io page {diagram.get('name', '')}: {exc}") from exc
    if decoded_models:
        wrapper = ET.Element("decodedDrawio")
        for model in decoded_models:
            wrapper.append(model)
        return wrapper
    return root


def decode_element_metadata(element: ET.Element, attribute: str) -> dict[str, Any] | None:
    raw = element.get(attribute)
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def drawio_page_models(path: Path) -> list[tuple[ET.Element | None, ET.Element]]:
    loaded = load_drawio_root(path)
    if loaded.tag == "mxGraphModel":
        return [(None, loaded)]
    if loaded.tag == "decodedDrawio":
        raw_root = ET.fromstring(path.read_bytes())
        diagrams = raw_root.findall(".//diagram")
        models = loaded.findall("./mxGraphModel")
        return [
            (diagrams[index] if index < len(diagrams) else None, model)
            for index, model in enumerate(models)
        ]
    pages: list[tuple[ET.Element | None, ET.Element]] = []
    for diagram in loaded.findall(".//diagram"):
        model = diagram.find("./mxGraphModel")
        if model is not None:
            pages.append((diagram, model))
    if pages:
        return pages
    return [(None, model) for model in loaded.findall(".//mxGraphModel")]


def extraction_text_lines(value: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</tr\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</td\s*>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" |")
        if line:
            lines.append(line)
    return lines


def extracted_number(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 3)


def unique_extracted_id(raw: str, used: set[str], prefix: str) -> str:
    candidate = raw
    for known_prefix in ("node-", "group-", "edge-", "page-"):
        if candidate.startswith(known_prefix):
            candidate = candidate[len(known_prefix):]
            break
    candidate = slugify(candidate or prefix)
    if candidate in {"0", "1"}:
        candidate = f"{prefix}-{candidate}"
    base = candidate
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def absolute_cell_box(
    cell: ET.Element,
    cell_map: dict[str, ET.Element],
    cache: dict[str, tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    cell_id = cell.get("id", "")
    if cell_id in cache:
        return cache[cell_id]
    geometry = cell.find("./mxGeometry")
    x = parse_number(geometry.get("x")) if geometry is not None else 0
    y = parse_number(geometry.get("y")) if geometry is not None else 0
    width = parse_number(geometry.get("width")) if geometry is not None else 0
    height = parse_number(geometry.get("height")) if geometry is not None else 0
    parent = cell_map.get(cell.get("parent", ""))
    if parent is not None and parent.get("vertex") == "1":
        parent_x, parent_y, _, _ = absolute_cell_box(parent, cell_map, cache)
        x += parent_x
        y += parent_y
    cache[cell_id] = (x, y, width, height)
    return cache[cell_id]


def infer_node_kind(styles: dict[str, str]) -> str:
    shape = styles.get("shape", "").lower()
    if shape == "cylinder3":
        return "database"
    if shape == "message":
        return "queue"
    if shape == "rhombus":
        return "decision"
    if shape == "process":
        return "process"
    if shape == "document":
        return "document"
    if shape == "note":
        return "note"
    if styles.get("dashed") == "1":
        return "external"
    return "service"


def infer_edge_kind(styles: dict[str, str]) -> str:
    if styles.get("endArrow") == "none":
        return "association"
    if styles.get("endArrow") == "open" and styles.get("dashed") == "1":
        return "async"
    if styles.get("dashed") == "1":
        return "dependency"
    return "sync"


def extracted_node_style(styles: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for drawio_key, ir_key in (
        ("fillColor", "fill"),
        ("strokeColor", "stroke"),
        ("fontColor", "font"),
    ):
        if is_hex_color(styles.get(drawio_key)):
            result[ir_key] = styles[drawio_key]
    if styles.get("dashed") in {"0", "1"}:
        result["dashed"] = styles["dashed"] == "1"
    if styles.get("rounded") in {"0", "1"}:
        result["rounded"] = styles["rounded"] == "1"
    return result


def inferred_port(styles: dict[str, str], prefix: str) -> tuple[str, float] | None:
    x_key, y_key = (
        ("exitX", "exitY") if prefix == "source" else ("entryX", "entryY")
    )
    if x_key not in styles or y_key not in styles:
        return None
    x, y = parse_number(styles[x_key], 0.5), parse_number(styles[y_key], 0.5)
    if x <= 0:
        return "west", max(0.0, min(1.0, y))
    if x >= 1:
        return "east", max(0.0, min(1.0, y))
    if y <= 0:
        return "north", max(0.0, min(1.0, x))
    if y >= 1:
        return "south", max(0.0, min(1.0, x))
    return None


def extracted_edge_style(styles: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if is_hex_color(styles.get("strokeColor")):
        result["color"] = styles["strokeColor"]
    width = parse_number(styles.get("strokeWidth"), 0)
    if width > 0:
        result["width"] = extracted_number(width)
    if styles.get("dashed") in {"0", "1"}:
        result["dashed"] = styles["dashed"] == "1"
    markers = {marker: cardinality for cardinality, marker in CARDINALITY_MARKERS.items()}
    start_cardinality = markers.get(styles.get("startArrow", ""))
    end_cardinality = markers.get(styles.get("endArrow", ""))
    if start_cardinality and end_cardinality:
        result["start_cardinality"] = start_cardinality
        result["end_cardinality"] = end_cardinality
    for prefix in ("source", "target"):
        port = inferred_port(styles, prefix)
        if port:
            result[f"{prefix}_port"] = port[0]
            result[f"{prefix}_offset"] = round(port[1], 4)
    return result


def group_for_box(
    box: tuple[float, float, float, float],
    group_boxes: dict[str, tuple[float, float, float, float]],
) -> str | None:
    center_x = box[0] + box[2] / 2
    center_y = box[1] + box[3] / 2
    candidates = [
        (width * height, group_id)
        for group_id, (x, y, width, height) in group_boxes.items()
        if x <= center_x <= x + width and y <= center_y <= y + height
    ]
    return min(candidates)[1] if candidates else None


def extract_drawio(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    page_models = drawio_page_models(path)
    if not page_models:
        raise ValueError("draw.io file contains no mxGraphModel pages")
    raw_document = ET.fromstring(path.read_bytes())
    metadata_version = raw_document.get("data-ir-version")
    metadata_contract = metadata_version == IR_METADATA_VERSION
    findings: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    used_page_ids: set[str] = set()
    summary = {
        "pages": 0,
        "groups": 0,
        "nodes": 0,
        "edges": 0,
        "metadata_cells": 0,
        "inferred_cells": 0,
        "inferred_pages": 0,
        "metadata_version": metadata_version,
    }
    if not metadata_contract:
        findings.append({
            "level": "warning",
            "code": "extract.metadata-version",
            "message": (
                "compiler metadata version is missing or unsupported; "
                "semantic recovery requires review"
            ),
        })

    for page_index, (diagram_element, model) in enumerate(page_models, start=1):
        page_metadata = (
            decode_element_metadata(diagram_element, "data-ir-page")
            if diagram_element is not None else None
        )
        raw_page_id = (
            str(page_metadata.get("id", ""))
            if page_metadata else str(
                (diagram_element.get("id", "") if diagram_element is not None else "")
                or (diagram_element.get("name", "") if diagram_element is not None else "")
                or f"page-{page_index}"
            )
        )
        page_id = unique_extracted_id(raw_page_id, used_page_ids, "page")
        page_title = str(
            (diagram_element.get("name", "") if diagram_element is not None else "")
            or (
                page_metadata.get("diagram", {}).get("title", "")
                if page_metadata and isinstance(page_metadata.get("diagram"), dict) else ""
            )
            or f"Page {page_index}"
        )
        if not page_metadata:
            summary["inferred_pages"] += 1

        cells = model.findall(".//mxCell")
        cell_map = {
            str(cell.get("id")): cell for cell in cells if cell.get("id") is not None
        }
        box_cache: dict[str, tuple[float, float, float, float]] = {}
        group_cells = [
            cell for cell in cells
            if cell.get("vertex") == "1"
            and parse_style_values(cell.get("style", "")).get("swimlane") == "1"
        ]
        group_cell_ids = {cell.get("id", "") for cell in group_cells}
        node_cells = [
            cell for cell in cells
            if cell.get("vertex") == "1"
            and cell.get("id", "") not in group_cell_ids
            and cell.get("id", "") not in {"0", "1"}
        ]
        edge_cells = [cell for cell in cells if cell.get("edge") == "1"]
        used_ids: set[str] = set()
        group_id_by_cell: dict[str, str] = {}
        group_boxes: dict[str, tuple[float, float, float, float]] = {}
        groups: list[dict[str, Any]] = []
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        for cell in group_cells:
            metadata = decode_element_metadata(cell, "data-ir")
            if metadata and metadata.get("id") and metadata.get("label"):
                summary["metadata_cells"] += 1
                raw_id = str(metadata["id"])
                group = copy.deepcopy(metadata)
            else:
                summary["inferred_cells"] += 1
                raw_id = cell.get("id", "") or "group"
                group = {}
            group_id = unique_extracted_id(raw_id, used_ids, "group")
            label_lines = extraction_text_lines(cell.get("value", ""))
            group.update({
                "id": group_id,
                "label": label_lines[0] if label_lines else str(group.get("label", group_id)),
            })
            groups.append(group)
            group_id_by_cell[cell.get("id", "")] = group_id
            group_boxes[group_id] = absolute_cell_box(cell, cell_map, box_cache)

        node_id_by_cell: dict[str, str] = {}
        for cell in node_cells:
            metadata = decode_element_metadata(cell, "data-ir")
            if metadata and metadata.get("id") and metadata.get("label"):
                summary["metadata_cells"] += 1
                raw_id = str(metadata["id"])
                node = copy.deepcopy(metadata)
            else:
                summary["inferred_cells"] += 1
                raw_id = cell.get("id", "") or "node"
                node = {}
            node_id = unique_extracted_id(raw_id, used_ids, "node")
            node_id_by_cell[cell.get("id", "")] = node_id
            box = absolute_cell_box(cell, cell_map, box_cache)
            styles = parse_style_values(cell.get("style", ""))
            lines = extraction_text_lines(cell.get("value", ""))
            kind = str(node.get("kind") or infer_node_kind(styles))
            node.update({
                "id": node_id,
                "label": lines[0] if lines else str(node.get("label", node_id)),
                "kind": kind,
                "position": {
                    "x": extracted_number(box[0]),
                    "y": extracted_number(box[1]),
                },
            })
            if box[2] > 0 and box[3] > 0:
                node["size"] = {
                    "width": extracted_number(box[2]),
                    "height": extracted_number(box[3]),
                }
            if kind != "entity":
                if len(lines) > 1:
                    node["description"] = " ".join(lines[1:])
                else:
                    node.pop("description", None)
            elif (
                metadata
                and cell.get("data-ir-value") is not None
                and cell.get("value", "") != cell.get("data-ir-value")
            ):
                summary["inferred_cells"] += 1
                findings.append({
                    "level": "warning",
                    "code": "extract.entity-visual-edit",
                    "message": "entity table text changed; field metadata was retained and should be reviewed",
                    "page": page_id,
                    "cell": cell.get("id", ""),
                })

            group_id = None
            metadata_group = node.get("group")
            if metadata_group and any(group["id"] == metadata_group for group in groups):
                group_id = str(metadata_group)
            elif cell.get("parent", "") in group_id_by_cell:
                group_id = group_id_by_cell[cell.get("parent", "")]
            else:
                group_id = group_for_box(box, group_boxes)
            if group_id:
                node["group"] = group_id
            else:
                node.pop("group", None)

            link = cell.get("link", "")
            page_link = re.fullmatch(r"data:page/id,page-(.+)", link)
            if page_link:
                node["link"] = slugify(page_link.group(1))
            elif link:
                node.pop("link", None)
                summary["inferred_cells"] += 1
                findings.append({
                    "level": "warning",
                    "code": "extract.unsupported-link",
                    "message": "external cell links are not representable as Diagram IR page links",
                    "page": page_id,
                    "cell": cell.get("id", ""),
                })
            elif "link" in node:
                node.pop("link")

            baseline_style = cell.get("data-ir-style")
            if not metadata or baseline_style != cell.get("style", ""):
                visible_style = extracted_node_style(styles)
                if visible_style:
                    node["style"] = {
                        **(
                            node.get("style", {})
                            if isinstance(node.get("style"), dict) else {}
                        ),
                        **visible_style,
                    }
            nodes.append(node)

        for cell in edge_cells:
            source = node_id_by_cell.get(cell.get("source", ""))
            target = node_id_by_cell.get(cell.get("target", ""))
            if not source or not target:
                findings.append({
                    "level": "error",
                    "code": "extract.edge-endpoint",
                    "message": "edge source and target must resolve to extracted nodes",
                    "page": page_id,
                    "cell": cell.get("id", ""),
                })
                continue
            metadata = decode_element_metadata(cell, "data-ir")
            if metadata and metadata.get("id"):
                summary["metadata_cells"] += 1
                raw_id = str(metadata["id"])
                edge = copy.deepcopy(metadata)
            else:
                summary["inferred_cells"] += 1
                raw_id = cell.get("id", "") or f"{source}-to-{target}"
                edge = {}
            edge_id = unique_extracted_id(raw_id, used_ids, "edge")
            styles = parse_style_values(cell.get("style", ""))
            label_lines = extraction_text_lines(cell.get("value", ""))
            edge.update({
                "id": edge_id,
                "from": source,
                "to": target,
                "label": " ".join(label_lines),
                "kind": str(edge.get("kind") or infer_edge_kind(styles)),
            })
            baseline_style = cell.get("data-ir-style")
            if not metadata or baseline_style != cell.get("style", ""):
                visible_style = extracted_edge_style(styles)
                if visible_style:
                    edge["style"] = {
                        **(
                            edge.get("style", {})
                            if isinstance(edge.get("style"), dict) else {}
                        ),
                        **visible_style,
                    }
            edges.append(edge)

        if page_metadata and isinstance(page_metadata.get("diagram"), dict):
            diagram_data = copy.deepcopy(page_metadata["diagram"])
        else:
            node_boxes = [
                absolute_cell_box(cell, cell_map, box_cache) for cell in node_cells
            ]
            x_span = (
                max((box[0] + box[2] for box in node_boxes), default=0)
                - min((box[0] for box in node_boxes), default=0)
            )
            y_span = (
                max((box[1] + box[3] for box in node_boxes), default=0)
                - min((box[1] for box in node_boxes), default=0)
            )
            diagram_data = {
                "direction": "LR" if x_span >= y_span else "TB",
                "theme": "light",
            }
            background = model.get("background")
            if is_hex_color(background):
                diagram_data["background"] = background
        diagram_data["title"] = page_title
        page = {
            "id": page_id,
            "title": page_title,
            "diagram": diagram_data,
            "groups": groups,
            "nodes": nodes,
            "edges": edges,
        }
        pages.append(page)
        summary["groups"] += len(groups)
        summary["nodes"] += len(nodes)
        summary["edges"] += len(edges)

    summary["pages"] = len(pages)
    if len(pages) == 1:
        only = pages[0]
        extracted = {
            "version": IR_VERSION,
            "diagram": only["diagram"],
            "groups": only["groups"],
            "nodes": only["nodes"],
            "edges": only["edges"],
        }
    else:
        extracted = {
            "version": IR_VERSION,
            "diagram": {},
            "pages": pages,
        }
    validation = validate_ir(extracted)
    for validation_issue in validation:
        if validation_issue["level"] == "error":
            finding = dict(validation_issue)
            finding["code"] = f"extract.{validation_issue['code']}"
            findings.append(finding)
    if summary["inferred_pages"]:
        findings.append({
            "level": "warning",
            "code": "extract.page-metadata",
            "message": (
                f"{summary['inferred_pages']} page(s) had no compiler metadata; "
                "title, direction, and theme were inferred"
            ),
        })
    inferred_cell_count = summary["inferred_cells"]
    if inferred_cell_count:
        findings.append({
            "level": "warning",
            "code": "extract.cell-metadata",
            "message": (
                f"{inferred_cell_count} cell(s) required semantic inference; "
                "review kinds, entity fields, styles, and links"
            ),
        })
    report = {
        "format": "drawio-extraction-report/v1",
        "source": str(path),
        "passed": not any(item["level"] == "error" for item in findings),
        "lossless": (
            metadata_contract
            and summary["inferred_cells"] == 0
            and summary["inferred_pages"] == 0
            and not any(item["level"] == "error" for item in findings)
        ),
        "summary": summary,
        "findings": findings,
    }
    return extracted, report


def rectangles_overlap(
    left: tuple[str, float, float, float, float],
    right: tuple[str, float, float, float, float],
) -> bool:
    return (
        left[1] < right[1] + right[3] and left[1] + left[3] > right[1]
        and left[2] < right[2] + right[4] and left[2] + left[4] > right[2]
    )


def orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(
    a: tuple[float, float], b: tuple[float, float],
    c: tuple[float, float], d: tuple[float, float],
) -> bool:
    first = orientation(a, b, c) * orientation(a, b, d)
    second = orientation(c, d, a) * orientation(c, d, b)
    return first < 0 and second < 0


def segment_crosses_rectangle(
    start: tuple[float, float], end: tuple[float, float],
    rectangle: tuple[str, float, float, float, float],
) -> bool:
    _, x, y, width, height = rectangle
    corners = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    if x < start[0] < x + width and y < start[1] < y + height:
        return True
    if x < end[0] < x + width and y < end[1] < y + height:
        return True
    return any(
        segments_cross(start, end, corners[index], corners[(index + 1) % 4])
        for index in range(4)
    )


def parse_style_values(style: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in style.split(";"):
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def validate_drawio(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    loaded_root = load_drawio_root(path)
    models = [loaded_root] if loaded_root.tag == "mxGraphModel" else loaded_root.findall(".//mxGraphModel")
    total_nodes = total_edges = total_groups = 0
    max_x = max_y = 0.0
    for page_index, model in enumerate(models, start=1):
        page_name = f"page-{page_index}"
        cells = model.findall(".//mxCell")
        ids: set[str] = set()
        cell_map: dict[str, ET.Element] = {}
        for cell in cells:
            cid = cell.get("id")
            if not cid:
                item = issue("error", "xml.id.missing", "mxCell is missing id")
                item["page"] = page_name
                issues.append(item)
                continue
            if cid in ids:
                item = issue("error", "xml.id.duplicate", f"duplicate cell id: {cid}", cid)
                item["page"] = page_name
                issues.append(item)
            ids.add(cid)
            cell_map[cid] = cell

        for cell in cells:
            cid = cell.get("id", "")
            parent = cell.get("parent")
            if parent and parent not in ids:
                item = issue("error", "xml.parent", f"missing parent: {parent}", cid)
                item["page"] = page_name
                issues.append(item)
            if cell.get("edge") == "1":
                for attr in ("source", "target"):
                    endpoint = cell.get(attr)
                    if not endpoint or endpoint not in ids:
                        item = issue("error", f"xml.edge.{attr}", f"missing {attr}: {endpoint}", cid)
                        item["page"] = page_name
                        issues.append(item)
                if cell.find("mxGeometry") is None:
                    item = issue("error", "xml.edge.geometry", "edge has no mxGeometry", cid)
                    item["page"] = page_name
                    issues.append(item)

        vertices: list[tuple[str, float, float, float, float]] = []
        groups: list[tuple[str, float, float, float, float]] = []
        group_ids = {cell.get("id") for cell in cells if "swimlane=1" in cell.get("style", "")}
        for cell in cells:
            cid = cell.get("id", "")
            if cell.get("vertex") != "1":
                continue
            geo = cell.find("mxGeometry")
            if geo is None:
                item = issue("error", "xml.vertex.geometry", "vertex has no mxGeometry", cid)
                item["page"] = page_name
                issues.append(item)
                continue
            box = (
                cid, parse_number(geo.get("x")), parse_number(geo.get("y")),
                parse_number(geo.get("width")), parse_number(geo.get("height")),
            )
            if cid in group_ids:
                groups.append(box)
                continue
            vertices.append(box)
            if box[1] < 0 or box[2] < 0:
                item = issue("warning", "layout.negative", "vertex has negative coordinates", cid)
                item["page"] = page_name
                issues.append(item)
            raw_label = cell.get("value", "")
            plain_label = re.sub(r"<[^>]+>", " ", raw_label)
            text_length = len(re.sub(r"\s+", " ", plain_label).strip())
            if box[3] > 0 and text_length * 6.3 > box[3] * max(1, math.ceil(box[4] / 24)):
                item = issue("warning", "label.clipping", "label may be clipped", cid)
                item["page"] = page_name
                issues.append(item)
            area = box[3] * box[4]
            density = text_length / (area / 1000) if area > 0 else 0
            if density > 5.5:
                item = issue(
                    "warning", "label.density",
                    f"text density is {density:.1f} characters per 1000px²; target at most 5.5",
                    cid,
                )
                item["page"] = page_name
                issues.append(item)
            styles = parse_style_values(cell.get("style", ""))
            fill, font = styles.get("fillColor"), styles.get("fontColor")
            if is_hex_color(fill) and is_hex_color(font):
                ratio = contrast_ratio(str(font), str(fill))
                if ratio < 4.5:
                    item = issue(
                        "warning", "node.contrast",
                        f"text contrast is {ratio:.2f}:1; target at least 4.5:1",
                        cid,
                    )
                    item["page"] = page_name
                    issues.append(item)

        for index, left in enumerate(vertices):
            for right in vertices[index + 1:]:
                if rectangles_overlap(left, right):
                    item = issue("error", "layout.overlap", f"overlaps {right[0]}", left[0])
                    item["page"] = page_name
                    issues.append(item)
        for index, left in enumerate(groups):
            for right in groups[index + 1:]:
                if rectangles_overlap(left, right):
                    item = issue("error", "layout.group-overlap", f"group overlaps {right[0]}", left[0])
                    item["page"] = page_name
                    issues.append(item)

        boxes = {box[0]: box for box in vertices}
        routed_edges: list[dict[str, Any]] = []
        for cell in cells:
            if cell.get("edge") != "1":
                continue
            source, target = cell.get("source", ""), cell.get("target", "")
            if source not in boxes or target not in boxes:
                continue
            source_box, target_box = boxes[source], boxes[target]
            styles = parse_style_values(cell.get("style", ""))
            exit_x = parse_number(styles.get("exitX"), 0.5)
            exit_y = parse_number(styles.get("exitY"), 0.5)
            entry_x = parse_number(styles.get("entryX"), 0.5)
            entry_y = parse_number(styles.get("entryY"), 0.5)
            start = (
                source_box[1] + source_box[3] * exit_x,
                source_box[2] + source_box[4] * exit_y,
            )
            end = (
                target_box[1] + target_box[3] * entry_x,
                target_box[2] + target_box[4] * entry_y,
            )
            geometry = cell.find("mxGeometry")
            waypoints = [
                (parse_number(point.get("x")), parse_number(point.get("y")))
                for point in (
                    geometry.findall("./Array[@as='points']/mxPoint")
                    if geometry is not None else []
                )
            ]
            points = simplify_route([start, *waypoints, end])
            segments = route_segments(points)
            routed_edges.append({
                "id": cell.get("id", ""),
                "nodes": {source, target},
                "segments": segments,
            })
            reported_nodes: set[str] = set()
            for segment_start, segment_end in segments:
                for other in vertices:
                    if other[0] in {source, target} or other[0] in reported_nodes:
                        continue
                    if segment_crosses_rectangle(segment_start, segment_end, other):
                        reported_nodes.add(other[0])
                        item = issue(
                            "warning", "routing.node-risk",
                            f"orthogonal route crosses {other[0]}",
                            cell.get("id", ""),
                        )
                        item["page"] = page_name
                        issues.append(item)
        for index, left in enumerate(routed_edges):
            for right in routed_edges[index + 1:]:
                if left["nodes"] & right["nodes"]:
                    continue
                crossing = any(
                    segments_cross(left_start, left_end, right_start, right_end)
                    for left_start, left_end in left["segments"]
                    for right_start, right_end in right["segments"]
                )
                if crossing:
                    item = issue(
                        "warning", "routing.crossing-risk",
                        f"route crosses {right['id']}", left["id"],
                    )
                    item["page"] = page_name
                    issues.append(item)

        page_max_x = max((x + width for _, x, _, width, _ in vertices), default=0)
        page_max_y = max((y + height for _, _, y, _, height in vertices), default=0)
        if page_max_x > 5000 or page_max_y > 5000:
            item = issue("warning", "layout.canvas", f"large canvas: {int(page_max_x)}×{int(page_max_y)}")
            item["page"] = page_name
            issues.append(item)
        total_nodes += len(vertices)
        total_edges += sum(1 for cell in cells if cell.get("edge") == "1")
        total_groups += len(group_ids)
        max_x, max_y = max(max_x, page_max_x), max(max_y, page_max_y)

    summary = {
        "pages": len(models),
        "nodes": total_nodes,
        "edges": total_edges,
        "groups": total_groups,
        "bounds": {"width": int(max_x), "height": int(max_y)},
    }
    return issues, summary


def score_issues(issues: list[dict[str, Any]]) -> int:
    score = 100
    for item in issues:
        score -= 20 if item["level"] == "error" else 5
    return max(0, score)


def print_report(issues: list[dict[str, Any]], summary: dict[str, Any] | None = None) -> None:
    payload = {
        "score": score_issues(issues),
        "errors": sum(1 for item in issues if item["level"] == "error"),
        "warnings": sum(1 for item in issues if item["level"] == "warning"),
        "issues": issues,
    }
    if summary is not None:
        payload["summary"] = summary
    print(json.dumps(payload, indent=2, ensure_ascii=False))


REPAIR_SUGGESTIONS = {
    "layout.overlap": "Move the reported nodes apart or regenerate the page with more spacing.",
    "layout.group-overlap": "Separate the group bands or split the page into smaller views.",
    "label.clipping": "Shorten the label, move detail into description, or increase node dimensions.",
    "label.density": "Reduce text or enlarge the node; keep one primary idea per node.",
    "node.contrast": "Choose text and fill colors with at least 4.5:1 contrast.",
    "theme.contrast": "Adjust the theme font or fill token to at least 4.5:1 contrast.",
    "routing.node-risk": "Add spacing, move the blocking node, or assign edge ports on a clearer side.",
    "routing.crossing-risk": "Reorder nodes, change direction, or assign ports that separate the routes.",
    "node.isolated": "Connect the node, explain why it is intentionally isolated, or remove it from the view.",
    "layout.canvas": "Split the diagram into linked pages or reduce its scope.",
    "erd.primary-key": "Declare a primary key or document why the entity is intentionally keyless.",
    "erd.type-mismatch": "Align the foreign-key type with the referenced key, including signedness and width.",
    "erd.reference-key": "Reference a primary-key or unique candidate-key field.",
    "erd.foreign-key": "Mark the child relationship field as a foreign key.",
    "erd.identifying-key": "Include the parent key in the child primary key or make the relationship non-identifying.",
    "ha.failure-domains": "Place redundant capacity in at least two independent failure domains.",
    "ha.replica-count": "Increase active-active or load-balancer replicas to at least two.",
    "ha.quorum": "Use an odd quorum of at least three voting members.",
    "ha.stateful-replication": "Add and label a synchronous or asynchronous replication path.",
    "ha.health-check": "Define the signal used to trigger automatic failover and its timeout.",
    "ha.cross-region-sync": "Confirm the latency budget or switch to asynchronous cross-region replication.",
    "ha.availability": "Define a measurable availability target such as 99.99%.",
    "ha.rto": "Define the maximum acceptable recovery time.",
    "ha.rpo": "Define the maximum acceptable data-loss window.",
    "ha.failover-replication": "Connect the stateful source and target with an explicit replication link.",
    "ha.failover-target": "Choose a standby, replica, active, or active-active promotion target.",
}


def build_audit_report(
    issues: list[dict[str, Any]], summary: dict[str, Any], previews: list[str] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in issues:
        code = str(item["code"])
        entry = grouped.setdefault(code, {
            "code": code,
            "suggestion": REPAIR_SUGGESTIONS.get(
                code, "Inspect the reported element and make the smallest source-level correction."
            ),
            "targets": [],
        })
        target = {"cell": item.get("cell"), "page": item.get("page"), "message": item["message"]}
        if target not in entry["targets"]:
            entry["targets"].append(target)
    return {
        "version": "1",
        "score": score_issues(issues),
        "errors": sum(1 for item in issues if item["level"] == "error"),
        "warnings": sum(1 for item in issues if item["level"] == "warning"),
        "summary": summary,
        "issues": issues,
        "repairs": list(grouped.values()),
        "visual_review": {
            "status": "required" if previews else "preview-not-generated",
            "previews": previews or [],
            "checklist": [
                "Verify the primary reading path and hierarchy.",
                "Inspect actual orthogonal edge crossings and stacked connectors.",
                "Confirm labels remain legible at normal zoom.",
                "Confirm color meaning is consistent and not the only differentiator.",
                "Confirm every page answers one architecture question.",
            ],
        },
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def collect_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                refs.add(child.rsplit("/", 1)[-1])
            else:
                refs.update(collect_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(collect_refs(child))
    return refs


def import_openapi(source: dict[str, Any], title: str | None = None) -> dict[str, Any]:
    info = source.get("info", {}) if isinstance(source.get("info"), dict) else {}
    api_title = title or str(info.get("title", "OpenAPI"))
    nodes: list[dict[str, Any]] = [
        {"id": "api", "label": api_title, "kind": "service", "description": "API surface"}
    ]
    edges: list[dict[str, Any]] = []
    groups = [{"id": "operations", "label": "Operations"}]
    schemas = source.get("components", {}).get("schemas", {}) if isinstance(source.get("components"), dict) else {}
    if not schemas and isinstance(source.get("definitions"), dict):
        schemas = source["definitions"]
    schema_ids: dict[str, str] = {}
    if isinstance(schemas, dict) and schemas:
        groups.append({"id": "schemas", "label": "Schemas"})
        for name in sorted(schemas):
            node_id = f"schema-{slugify(name)}"
            schema_ids[str(name)] = node_id
            schema = schemas[name] if isinstance(schemas[name], dict) else {}
            required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
            nodes.append({
                "id": node_id,
                "label": str(name),
                "kind": "database",
                "group": "schemas",
                "description": f"{len(schema.get('properties', {}))} fields · {len(required)} required",
            })
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    paths = source.get("paths", {}) if isinstance(source.get("paths"), dict) else {}
    used_ids: set[str] = {"api", *schema_ids.values()}
    for path_name in sorted(paths):
        path_item = paths[path_name] if isinstance(paths[path_name], dict) else {}
        for method in sorted(methods & set(path_item)):
            operation = path_item[method] if isinstance(path_item[method], dict) else {}
            raw_id = str(operation.get("operationId") or f"{method}-{path_name}")
            base_id = f"op-{slugify(raw_id)}"
            node_id = base_id
            suffix = 2
            while node_id in used_ids:
                node_id = f"{base_id}-{suffix}"
                suffix += 1
            used_ids.add(node_id)
            summary = str(operation.get("summary") or operation.get("operationId") or path_name)
            nodes.append({
                "id": node_id, "label": summary, "kind": "process", "group": "operations",
                "description": f"{method.upper()} {path_name}",
            })
            edges.append({
                "id": f"api-to-{node_id}", "from": "api", "to": node_id,
                "label": method.upper(), "kind": "sync",
            })
            for schema_name in sorted(collect_refs(operation)):
                if schema_name in schema_ids:
                    edges.append({
                        "id": f"{node_id}-uses-{schema_ids[schema_name]}",
                        "from": node_id, "to": schema_ids[schema_name],
                        "label": "uses", "kind": "data",
                    })
    return {
        "version": "1",
        "diagram": {"title": f"{api_title} API", "direction": "LR", "theme": "colorblind"},
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def split_sql_columns(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def normalize_sql_name(value: str) -> str:
    return value.strip().strip("`\"[]").split(".")[-1].strip("`\"[]")


def import_sql(text: str, title: str | None = None) -> dict[str, Any]:
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[\]\w.]+)\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    tables: dict[str, dict[str, Any]] = {}
    relations: list[tuple[str, str, str]] = []
    for match in pattern.finditer(text):
        table_name = normalize_sql_name(match.group(1))
        columns: list[str] = []
        primary_keys: list[str] = []
        for definition in split_sql_columns(match.group(2)):
            table_pk = re.match(r"(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)", definition, re.I)
            table_fk = re.match(
                r"(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+([`\"\[\]\w.]+)",
                definition, re.I,
            )
            if table_pk:
                primary_keys.extend(normalize_sql_name(item) for item in table_pk.group(1).split(","))
                continue
            if table_fk:
                local = normalize_sql_name(table_fk.group(1).split(",")[0])
                relations.append((table_name, normalize_sql_name(table_fk.group(2)), local))
                continue
            column_match = re.match(r"([`\"\[\]\w]+)\s+(.+)", definition, re.I | re.S)
            if not column_match:
                continue
            column_name = normalize_sql_name(column_match.group(1))
            columns.append(column_name)
            remainder = column_match.group(2)
            if re.search(r"\bPRIMARY\s+KEY\b", remainder, re.I):
                primary_keys.append(column_name)
            inline_fk = re.search(r"\bREFERENCES\s+([`\"\[\]\w.]+)", remainder, re.I)
            if inline_fk:
                relations.append((table_name, normalize_sql_name(inline_fk.group(1)), column_name))
        tables[table_name] = {"columns": columns, "primary_keys": primary_keys}
    if not tables:
        raise ValueError("no CREATE TABLE statements found")
    referenced = {target for _, target, _ in relations}
    nodes = []
    for table_name in sorted(set(tables) | referenced):
        if table_name in tables:
            table = tables[table_name]
            pk_text = ", ".join(table["primary_keys"]) or "none"
            description = f"{len(table['columns'])} columns · PK: {pk_text}"
            kind = "database"
        else:
            description, kind = "Referenced external table", "external"
        nodes.append({
            "id": f"table-{slugify(table_name)}", "label": table_name, "kind": kind,
            "group": "tables", "description": description,
        })
    edges = [
        {
            "id": f"fk-{slugify(source)}-{slugify(target)}-{slugify(column)}",
            "from": f"table-{slugify(source)}", "to": f"table-{slugify(target)}",
            "label": f"FK {column}", "kind": "data",
        }
        for source, target, column in relations
    ]
    return {
        "version": "1",
        "diagram": {"title": title or "Database schema", "direction": "LR", "theme": "colorblind"},
        "groups": [{"id": "tables", "label": "Tables"}],
        "nodes": nodes,
        "edges": edges,
    }


def import_compose(source: dict[str, Any], title: str | None = None) -> dict[str, Any]:
    services = source.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("compose file has no services")
    groups = [{"id": "services", "label": "Services"}]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    service_ids = {str(name): f"service-{slugify(str(name))}" for name in services}
    for name in sorted(services):
        config = services[name] if isinstance(services[name], dict) else {}
        image = str(config.get("image") or config.get("build") or "local")
        lowered = f"{name} {image}".lower()
        kind = "database" if any(token in lowered for token in ("postgres", "mysql", "mongo", "redis", "mariadb")) else "service"
        nodes.append({
            "id": service_ids[str(name)], "label": str(name), "kind": kind,
            "group": "services", "description": image,
        })
        depends = config.get("depends_on", [])
        dependency_names = list(depends) if isinstance(depends, (list, dict)) else []
        for dependency in sorted(str(item) for item in dependency_names):
            if dependency in service_ids:
                edges.append({
                    "id": f"{service_ids[str(name)]}-depends-{service_ids[dependency]}",
                    "from": service_ids[str(name)], "to": service_ids[dependency],
                    "label": "depends on", "kind": "dependency",
                })
    volumes = source.get("volumes", {})
    if isinstance(volumes, dict) and volumes:
        groups.append({"id": "volumes", "label": "Volumes"})
        for volume_name in sorted(volumes):
            volume_id = f"volume-{slugify(str(volume_name))}"
            nodes.append({
                "id": volume_id, "label": str(volume_name), "kind": "database",
                "group": "volumes", "description": "Named volume",
            })
            for service_name, config in services.items():
                mounts = config.get("volumes", []) if isinstance(config, dict) else []
                for mount in mounts if isinstance(mounts, list) else []:
                    source_name = str(mount).split(":", 1)[0] if not isinstance(mount, dict) else str(mount.get("source", ""))
                    if source_name == volume_name:
                        edges.append({
                            "id": f"{service_ids[str(service_name)]}-mounts-{volume_id}",
                            "from": service_ids[str(service_name)], "to": volume_id,
                            "label": "mounts", "kind": "data",
                        })
    return {
        "version": "1",
        "diagram": {"title": title or "Docker Compose", "direction": "LR", "theme": "colorblind"},
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


IGNORED_SOURCE_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "dist", "build",
    "__pycache__", ".next", ".turbo", "coverage",
}


def discover_source_files(root: Path, suffixes: set[str], max_files: int) -> list[Path]:
    if not root.is_dir():
        raise ValueError(f"source root is not a directory: {root}")
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and not (set(path.relative_to(root).parts) & IGNORED_SOURCE_DIRS)
    )
    if len(files) > max_files:
        raise ValueError(f"source tree has {len(files)} matching files; raise --max-files above {max_files} explicitly")
    return files


def unique_prefixed_ids(names: list[str], prefix: str) -> dict[str, str]:
    result: dict[str, str] = {}
    used: set[str] = set()
    for name in sorted(names):
        base = f"{prefix}-{slugify(name)}"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        result[name] = candidate
        used.add(candidate)
    return result


def unique_module_ids(relative_names: list[str]) -> dict[str, str]:
    return unique_prefixed_ids(relative_names, "module")


def code_groups(relative_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    group_labels = sorted({path.parts[0] for path in relative_paths if len(path.parts) > 1})
    groups = [{"id": f"package-{slugify(label)}", "label": label} for label in group_labels]
    mapping = {label: f"package-{slugify(label)}" for label in group_labels}
    return groups, mapping


def import_python_tree(root: Path, title: str | None = None, max_files: int = 500) -> dict[str, Any]:
    files = discover_source_files(root, {".py"}, max_files)
    if not files:
        raise ValueError("no Python source files found")
    module_files: dict[str, Path] = {}
    relative_paths: dict[str, Path] = {}
    for path in files:
        relative = path.relative_to(root)
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module = ".".join(parts) or root.name
        module_files[module] = path
        relative_paths[module] = relative
    module_ids = unique_module_ids(list(module_files))
    groups, group_mapping = code_groups(list(relative_paths.values()))
    nodes: list[dict[str, Any]] = []
    for module in sorted(module_files):
        relative = relative_paths[module]
        node: dict[str, Any] = {
            "id": module_ids[module], "label": module, "kind": "service",
            "description": str(relative),
        }
        if len(relative.parts) > 1:
            node["group"] = group_mapping[relative.parts[0]]
        nodes.append(node)

    def resolve_module(name: str) -> str | None:
        candidate = name
        while candidate:
            if candidate in module_files:
                return candidate
            candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
        return None

    relations: set[tuple[str, str]] = set()
    for module in sorted(module_files):
        path = module_files[module]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError(f"cannot parse {path.relative_to(root)}: {exc}") from exc
        package_parts = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    keep = max(0, len(package_parts) - (node.level - 1))
                    base = package_parts[:keep]
                    if node.module:
                        base.extend(node.module.split("."))
                    base_name = ".".join(base)
                elif node.module:
                    base_name = node.module
                else:
                    base_name = ""
                for alias in node.names:
                    if alias.name == "*":
                        if base_name:
                            imported.add(base_name)
                    else:
                        imported.add(f"{base_name}.{alias.name}".strip("."))
        for dependency in imported:
            resolved = resolve_module(dependency)
            if resolved and resolved != module:
                relations.add((module, resolved))
    edges = [
        {
            "id": f"{module_ids[source]}-imports-{module_ids[target]}",
            "from": module_ids[source], "to": module_ids[target],
            "label": "imports", "kind": "dependency",
        }
        for source, target in sorted(relations)
    ]
    return {
        "version": "1",
        "diagram": {"title": title or f"{root.name} Python modules", "direction": "LR", "theme": "colorblind"},
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def import_typescript_tree(root: Path, title: str | None = None, max_files: int = 500) -> dict[str, Any]:
    suffixes = {".ts", ".tsx", ".js", ".jsx"}
    files = discover_source_files(root, suffixes, max_files)
    files = [path for path in files if not path.name.endswith(".d.ts")]
    if not files:
        raise ValueError("no TypeScript or JavaScript source files found")
    relative_paths = {str(path.relative_to(root).with_suffix("")): path.relative_to(root) for path in files}
    module_ids = unique_module_ids(list(relative_paths))
    absolute_to_name = {path.resolve(): name for name, path in ((name, root / rel) for name, rel in relative_paths.items())}
    groups, group_mapping = code_groups(list(relative_paths.values()))
    nodes: list[dict[str, Any]] = []
    for name in sorted(relative_paths):
        relative = relative_paths[name]
        node: dict[str, Any] = {
            "id": module_ids[name], "label": name.replace("/", "."), "kind": "service",
            "description": str(relative),
        }
        if len(relative.parts) > 1:
            node["group"] = group_mapping[relative.parts[0]]
        nodes.append(node)

    def resolve_relative(source_file: Path, specifier: str) -> str | None:
        if not specifier.startswith("."):
            return None
        base = (source_file.parent / specifier).resolve()
        candidates = [base]
        candidates.extend(Path(f"{base}{suffix}") for suffix in sorted(suffixes))
        candidates.extend((base / f"index{suffix}") for suffix in sorted(suffixes))
        for candidate in candidates:
            if candidate in absolute_to_name:
                return absolute_to_name[candidate]
        return None

    pattern = re.compile(
        r"(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?[\"']([^\"']+)[\"']"
        r"|require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
        r"|import\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
    )
    relations: set[tuple[str, str]] = set()
    for name in sorted(relative_paths):
        source_file = (root / relative_paths[name]).resolve()
        try:
            text = source_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"cannot read {relative_paths[name]}: {exc}") from exc
        for match in pattern.finditer(text):
            specifier = next(value for value in match.groups() if value is not None)
            resolved = resolve_relative(source_file, specifier)
            if resolved and resolved != name:
                relations.add((name, resolved))
    edges = [
        {
            "id": f"{module_ids[source]}-imports-{module_ids[target]}",
            "from": module_ids[source], "to": module_ids[target],
            "label": "imports", "kind": "dependency",
        }
        for source, target in sorted(relations)
    ]
    return {
        "version": "1",
        "diagram": {
            "title": title or f"{root.name} TypeScript modules",
            "direction": "LR", "theme": "colorblind",
        },
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def discover_input_files(
    path: Path, suffixes: set[str], max_files: int, preferred_names: set[str] | None = None,
) -> list[Path]:
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(
            item for item in path.rglob("*")
            if item.is_file()
            and (
                item.suffix.lower() in suffixes
                or (preferred_names is not None and item.name in preferred_names)
            )
            and not (set(item.relative_to(path).parts) & IGNORED_SOURCE_DIRS)
        )
    else:
        raise ValueError(f"input does not exist: {path}")
    if len(files) > max_files:
        raise ValueError(
            f"input has {len(files)} matching files; raise --max-files above {max_files} explicitly"
        )
    return files


def hcl_blocks(text: str) -> list[tuple[str, list[str], str]]:
    """Return top-level Terraform blocks without requiring an HCL dependency."""
    header = re.compile(
        r'(?m)^\s*(resource|data|module)\s+"([^"]+)"'
        r'(?:\s+"([^"]+)")?\s*\{'
    )
    blocks: list[tuple[str, list[str], str]] = []
    for match in header.finditer(text):
        depth = 1
        index = match.end()
        quote: str | None = None
        escaped = False
        line_comment = False
        block_comment = False
        while index < len(text) and depth:
            char = text[index]
            following = text[index:index + 2]
            if line_comment:
                if char == "\n":
                    line_comment = False
            elif block_comment:
                if following == "*/":
                    block_comment = False
                    index += 1
            elif quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif following == "//" or char == "#":
                line_comment = True
                if following == "//":
                    index += 1
            elif following == "/*":
                block_comment = True
                index += 1
            elif char in {'"', "'"}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        if depth:
            raise ValueError(f"unclosed Terraform {match.group(1)} block: {match.group(2)}")
        labels = [match.group(2)]
        if match.group(3):
            labels.append(match.group(3))
        blocks.append((match.group(1), labels, text[match.end():index - 1]))
    return blocks


def terraform_kind(address: str) -> str:
    lowered = address.lower()
    if any(token in lowered for token in (
        "db_", "database", "rds", "dynamodb", "elasticache", "redis", "storage",
        "bucket", "volume", "disk",
    )):
        return "database"
    if any(token in lowered for token in (
        "queue", "topic", "sns", "sqs", "pubsub", "eventhub", "kafka",
    )):
        return "queue"
    if address.startswith(("data.", "module.")):
        return "external"
    return "service"


def import_terraform(
    path: Path, title: str | None = None, max_files: int = 500,
) -> dict[str, Any]:
    files = discover_input_files(path, {".tf"}, max_files)
    if not files:
        raise ValueError("no Terraform .tf files found")
    base = path if path.is_dir() else path.parent
    records: list[dict[str, str]] = []
    for source_file in files:
        relative = str(source_file.relative_to(base)) if source_file != path else source_file.name
        text = source_file.read_text(encoding="utf-8")
        for block_type, labels, body in hcl_blocks(text):
            if block_type == "module":
                address = f"module.{labels[0]}"
                label = labels[0]
            elif block_type == "data":
                address = f"data.{labels[0]}.{labels[1]}"
                label = f"{labels[0]}.{labels[1]}"
            else:
                address = f"{labels[0]}.{labels[1]}"
                label = f"{labels[0]}.{labels[1]}"
            records.append({
                "address": address, "label": label, "block_type": block_type,
                "body": body, "file": relative,
            })
    if not records:
        raise ValueError("no Terraform resource, data, or module blocks found")
    addresses = sorted({record["address"] for record in records})
    ids = unique_module_ids(addresses)
    file_names = sorted({record["file"] for record in records})
    group_ids = unique_prefixed_ids(file_names, "terraform")
    groups = [{"id": group_ids[name], "label": name} for name in file_names]
    by_address = {record["address"]: record for record in records}
    nodes = [
        {
            "id": ids[address],
            "label": by_address[address]["label"],
            "kind": terraform_kind(address),
            "group": group_ids[by_address[address]["file"]],
            "description": (
                f"{by_address[address]['block_type']} · {by_address[address]['file']} · {address}"
            ),
        }
        for address in addresses
    ]
    reference_pattern = re.compile(
        r"\b("
        r"data\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
        r"|module\.[A-Za-z0-9_-]+"
        r"|[A-Za-z][A-Za-z0-9_-]*\.[A-Za-z0-9_-]+"
        r")\b"
    )
    ignored_prefixes = {
        "var", "local", "each", "count", "path", "terraform", "self",
    }
    relations: set[tuple[str, str]] = set()
    for record in records:
        for reference in reference_pattern.findall(record["body"]):
            if reference.split(".", 1)[0] in ignored_prefixes:
                continue
            if reference in ids and reference != record["address"]:
                relations.add((record["address"], reference))
    edges = [
        {
            "id": f"{ids[source]}-depends-{ids[target]}",
            "from": ids[source], "to": ids[target],
            "label": "depends on", "kind": "dependency",
        }
        for source, target in sorted(relations)
    ]
    return {
        "version": "1",
        "diagram": {
            "title": title or f"{path.stem if path.is_file() else path.name} Terraform",
            "direction": "LR", "theme": "colorblind",
        },
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def load_document_stream(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        loaded = json.loads(text)
        values = loaded if isinstance(loaded, list) else [loaded]
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "YAML manifest input requires PyYAML; use JSON or install pyyaml"
            ) from exc
        values = list(yaml.safe_load_all(text))
    documents: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        if value.get("kind") == "List" and isinstance(value.get("items"), list):
            documents.extend(item for item in value["items"] if isinstance(item, dict))
        else:
            documents.append(value)
    return documents


def kubernetes_kind(kind: str) -> str:
    if kind in {"ConfigMap", "Secret"}:
        return "document"
    if kind in {"PersistentVolume", "PersistentVolumeClaim", "StorageClass"}:
        return "database"
    if kind in {"Ingress", "Gateway", "HTTPRoute", "LoadBalancer"}:
        return "external"
    if kind in {"Job", "CronJob"}:
        return "process"
    return "service"


def kubernetes_pod_spec(resource: dict[str, Any]) -> dict[str, Any]:
    spec = resource.get("spec", {}) if isinstance(resource.get("spec"), dict) else {}
    kind = str(resource.get("kind", ""))
    if kind == "CronJob":
        return (
            spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
            if isinstance(spec.get("jobTemplate"), dict) else {}
        )
    template = spec.get("template", {}) if isinstance(spec.get("template"), dict) else {}
    return template.get("spec", {}) if isinstance(template.get("spec"), dict) else {}


def import_kubernetes(
    path: Path, title: str | None = None, max_files: int = 500,
) -> dict[str, Any]:
    files = discover_input_files(path, {".json", ".yaml", ".yml"}, max_files)
    if not files:
        raise ValueError("no Kubernetes JSON or YAML manifests found")
    resources: list[dict[str, Any]] = []
    for source_file in files:
        resources.extend(load_document_stream(source_file))
    resources = [
        resource for resource in resources
        if resource.get("kind")
        and isinstance(resource.get("metadata"), dict)
        and resource["metadata"].get("name")
    ]
    if not resources:
        raise ValueError("no Kubernetes resources with kind and metadata.name found")
    keyed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for resource in resources:
        metadata = resource["metadata"]
        namespace = str(metadata.get("namespace") or "default")
        key = (namespace, str(resource["kind"]), str(metadata["name"]))
        keyed[key] = resource
    namespaces = sorted({key[0] for key in keyed})
    group_ids = unique_prefixed_ids(namespaces, "namespace")
    groups = [
        {"id": group_ids[namespace], "label": f"namespace/{namespace}"}
        for namespace in namespaces
    ]
    resource_addresses = {
        key: f"{key[0]}/{key[1]}/{key[2]}" for key in keyed
    }
    address_ids = unique_prefixed_ids(list(resource_addresses.values()), "k8s")
    resource_ids = {
        key: address_ids[address] for key, address in resource_addresses.items()
    }
    nodes = []
    for key in sorted(keyed):
        namespace, kind, name = key
        resource = keyed[key]
        spec = resource.get("spec", {}) if isinstance(resource.get("spec"), dict) else {}
        details: list[str] = [kind, f"namespace/{namespace}"]
        if kind in {"Deployment", "StatefulSet", "DaemonSet"}:
            details.append(f"replicas={spec.get('replicas', 1)}")
        if kind == "Service":
            details.append(f"type={spec.get('type', 'ClusterIP')}")
        if kind == "Secret":
            details.append("metadata only; values redacted")
        nodes.append({
            "id": resource_ids[key], "label": name, "kind": kubernetes_kind(kind),
            "group": group_ids[namespace], "description": " · ".join(details),
        })

    relations: set[tuple[tuple[str, str, str], tuple[str, str, str], str, str]] = set()
    workloads = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}
    for key in sorted(keyed):
        namespace, kind, _ = key
        resource = keyed[key]
        metadata = resource.get("metadata", {})
        spec = resource.get("spec", {}) if isinstance(resource.get("spec"), dict) else {}
        for owner in metadata.get("ownerReferences", []) if isinstance(metadata.get("ownerReferences"), list) else []:
            if not isinstance(owner, dict):
                continue
            target = (namespace, str(owner.get("kind", "")), str(owner.get("name", "")))
            if target in keyed:
                relations.add((target, key, "owns", "dependency"))
        if kind == "Service":
            selector = spec.get("selector", {}) if isinstance(spec.get("selector"), dict) else {}
            if selector:
                for target, candidate in keyed.items():
                    if target[0] != namespace or target[1] not in workloads:
                        continue
                    candidate_spec = candidate.get("spec", {}) if isinstance(candidate.get("spec"), dict) else {}
                    template = candidate_spec.get("template", {}) if isinstance(candidate_spec.get("template"), dict) else {}
                    template_metadata = (
                        template.get("metadata", {}) if isinstance(template.get("metadata"), dict) else {}
                    )
                    labels = template_metadata.get("labels", {})
                    if target[1] == "Pod":
                        labels = candidate.get("metadata", {}).get("labels", {})
                    if isinstance(labels, dict) and all(labels.get(name) == value for name, value in selector.items()):
                        relations.add((key, target, "selects", "sync"))
        if kind in {"Ingress", "HTTPRoute"}:
            backend_names: set[str] = set()
            default_backend = spec.get("defaultBackend", {})
            if isinstance(default_backend, dict):
                service = default_backend.get("service", {})
                if isinstance(service, dict) and service.get("name"):
                    backend_names.add(str(service["name"]))
                elif default_backend.get("serviceName"):
                    backend_names.add(str(default_backend["serviceName"]))
            for rule in spec.get("rules", []) if isinstance(spec.get("rules"), list) else []:
                if not isinstance(rule, dict):
                    continue
                http = rule.get("http", {}) if isinstance(rule.get("http"), dict) else {}
                paths = http.get("paths", []) if isinstance(http.get("paths"), list) else []
                for route_path in paths:
                    backend = route_path.get("backend", {}) if isinstance(route_path, dict) else {}
                    service = backend.get("service", {}) if isinstance(backend.get("service"), dict) else {}
                    name = service.get("name") or backend.get("serviceName")
                    if name:
                        backend_names.add(str(name))
                for backend in rule.get("backendRefs", []) if isinstance(rule.get("backendRefs"), list) else []:
                    if isinstance(backend, dict) and backend.get("name"):
                        backend_names.add(str(backend["name"]))
            for backend_name in sorted(backend_names):
                target = (namespace, "Service", backend_name)
                if target in keyed:
                    relations.add((key, target, "routes", "sync"))
        if kind in workloads:
            pod_spec = spec if kind == "Pod" else kubernetes_pod_spec(resource)
            config_refs: set[tuple[str, str]] = set()
            for container in pod_spec.get("containers", []) if isinstance(pod_spec.get("containers"), list) else []:
                if not isinstance(container, dict):
                    continue
                for env_from in container.get("envFrom", []) if isinstance(container.get("envFrom"), list) else []:
                    if not isinstance(env_from, dict):
                        continue
                    for field, target_kind in (("configMapRef", "ConfigMap"), ("secretRef", "Secret")):
                        reference = env_from.get(field, {})
                        if isinstance(reference, dict) and reference.get("name"):
                            config_refs.add((target_kind, str(reference["name"])))
                for env in container.get("env", []) if isinstance(container.get("env"), list) else []:
                    value_from = env.get("valueFrom", {}) if isinstance(env, dict) else {}
                    for field, target_kind in (("configMapKeyRef", "ConfigMap"), ("secretKeyRef", "Secret")):
                        reference = value_from.get(field, {}) if isinstance(value_from, dict) else {}
                        if isinstance(reference, dict) and reference.get("name"):
                            config_refs.add((target_kind, str(reference["name"])))
            for volume in pod_spec.get("volumes", []) if isinstance(pod_spec.get("volumes"), list) else []:
                if not isinstance(volume, dict):
                    continue
                for field, target_kind in (
                    ("configMap", "ConfigMap"), ("secret", "Secret"),
                    ("persistentVolumeClaim", "PersistentVolumeClaim"),
                ):
                    reference = volume.get(field, {})
                    if not isinstance(reference, dict):
                        continue
                    name = reference.get("claimName") if target_kind == "PersistentVolumeClaim" else reference.get("name") or reference.get("secretName")
                    if name:
                        config_refs.add((target_kind, str(name)))
            for target_kind, name in sorted(config_refs):
                target = (namespace, target_kind, name)
                if target in keyed:
                    relations.add((key, target, "uses", "data"))
    edges = [
        {
            "id": (
                f"{resource_ids[source]}-{slugify(label)}-{resource_ids[target]}"
            ),
            "from": resource_ids[source], "to": resource_ids[target],
            "label": label, "kind": edge_kind,
        }
        for source, target, label, edge_kind in sorted(relations)
    ]
    return {
        "version": "1",
        "diagram": {
            "title": title or f"{path.stem if path.is_file() else path.name} Kubernetes",
            "direction": "LR", "theme": "colorblind",
        },
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def pipeline_files(
    path: Path, pipeline_type: str, max_files: int,
) -> list[Path]:
    if path.is_file():
        return [path]
    if pipeline_type == "github-actions":
        workflows = path / ".github" / "workflows"
        if not workflows.is_dir():
            workflows = path
        return discover_input_files(workflows, {".json", ".yaml", ".yml"}, max_files)
    return discover_input_files(
        path, {".json", ".yaml", ".yml"}, max_files,
        preferred_names={".gitlab-ci.yml", ".gitlab-ci.yaml"},
    )


def import_github_actions(
    path: Path, title: str | None = None, max_files: int = 500,
) -> dict[str, Any]:
    files = pipeline_files(path, "github-actions", max_files)
    workflows: list[tuple[Path, dict[str, Any]]] = []
    for source_file in files:
        loaded = load_data(source_file)
        if isinstance(loaded.get("jobs"), dict):
            workflows.append((source_file, loaded))
    if not workflows:
        raise ValueError("no GitHub Actions workflows with jobs found")
    groups: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    base = path if path.is_dir() else path.parent
    workflow_names = [
        str(source_file.relative_to(base)) if source_file != path else source_file.name
        for source_file, _ in workflows
    ]
    workflow_ids = unique_prefixed_ids(workflow_names, "workflow")
    for source_file, workflow in sorted(workflows, key=lambda item: str(item[0])):
        workflow_name = (
            str(source_file.relative_to(base)) if source_file != path else source_file.name
        )
        workflow_id = workflow_ids[workflow_name]
        groups.append({
            "id": workflow_id,
            "label": str(workflow.get("name") or source_file.stem),
        })
        jobs = workflow["jobs"]
        local_job_ids = unique_prefixed_ids(
            [str(name) for name in jobs], f"{workflow_id}-job",
        )
        job_ids = {str(name): local_job_ids[str(name)] for name in jobs}
        reusable_names = sorted({
            str(config["uses"])
            for config in jobs.values()
            if isinstance(config, dict) and config.get("uses")
        })
        reusable_ids = unique_prefixed_ids(
            reusable_names, f"{workflow_id}-reusable",
        )
        for reusable in reusable_names:
            nodes.append({
                "id": reusable_ids[reusable],
                "label": reusable.split("@", 1)[0],
                "kind": "external",
                "group": workflow_id,
                "description": reusable,
            })
        for name in sorted(jobs):
            config = jobs[name] if isinstance(jobs[name], dict) else {}
            description = str(config.get("runs-on") or config.get("uses") or "job")
            nodes.append({
                "id": job_ids[str(name)],
                "label": str(config.get("name") or name),
                "kind": "process",
                "group": workflow_id,
                "description": description,
            })
            needs = config.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            if isinstance(needs, list):
                for dependency in sorted(str(item) for item in needs):
                    if dependency in job_ids:
                        edges.append({
                            "id": f"{job_ids[dependency]}-before-{job_ids[str(name)]}",
                            "from": job_ids[dependency], "to": job_ids[str(name)],
                            "label": "needs", "kind": "dependency",
                        })
            reusable = str(config.get("uses", ""))
            if reusable in reusable_ids:
                edges.append({
                    "id": f"{job_ids[str(name)]}-calls-{reusable_ids[reusable]}",
                    "from": job_ids[str(name)], "to": reusable_ids[reusable],
                    "label": "calls", "kind": "dependency",
                })
    return {
        "version": "1",
        "diagram": {
            "title": title or f"{path.stem if path.is_file() else path.name} GitHub Actions",
            "direction": "TB", "theme": "colorblind",
        },
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


GITLAB_RESERVED_KEYS = {
    "default", "include", "stages", "variables", "workflow", "image", "services",
    "before_script", "after_script", "cache", "pages", "interruptible",
}


def import_gitlab_ci(
    path: Path, title: str | None = None, max_files: int = 500,
) -> dict[str, Any]:
    files = pipeline_files(path, "gitlab-ci", max_files)
    if not files:
        raise ValueError("no GitLab CI files found")
    source_file = next(
        (item for item in files if item.name in {".gitlab-ci.yml", ".gitlab-ci.yaml"}),
        files[0],
    )
    source = load_data(source_file)
    jobs = {
        str(name): config for name, config in source.items()
        if name not in GITLAB_RESERVED_KEYS
        and not str(name).startswith(".")
        and isinstance(config, dict)
        and any(key in config for key in ("script", "trigger", "stage"))
    }
    if not jobs:
        raise ValueError("no GitLab CI jobs found")
    declared_stages = source.get("stages", [])
    stage_names = [str(item) for item in declared_stages] if isinstance(declared_stages, list) else []
    for config in jobs.values():
        stage = str(config.get("stage", "test"))
        if stage not in stage_names:
            stage_names.append(stage)
    group_ids = {stage: f"stage-{slugify(stage)}" for stage in stage_names}
    groups = [{"id": group_ids[stage], "label": stage} for stage in stage_names]
    job_ids = unique_prefixed_ids(list(jobs), "gitlab-job")
    nodes = [
        {
            "id": job_ids[name],
            "label": name,
            "kind": "process",
            "group": group_ids[str(jobs[name].get("stage", "test"))],
            "description": (
                "trigger" if "trigger" in jobs[name]
                else f"{len(jobs[name].get('script', [])) if isinstance(jobs[name].get('script'), list) else 1} script step(s)"
            ),
        }
        for name in sorted(jobs)
    ]
    relations: set[tuple[str, str, str]] = set()
    explicit_jobs: set[str] = set()
    for name, config in jobs.items():
        needs = config.get("needs", config.get("dependencies", []))
        if isinstance(needs, str):
            needs = [needs]
        if isinstance(needs, list) and needs:
            explicit_jobs.add(name)
            for dependency in needs:
                dependency_name = (
                    str(dependency.get("job")) if isinstance(dependency, dict) else str(dependency)
                )
                if dependency_name in jobs and dependency_name != name:
                    relations.add((dependency_name, name, "needs"))
    jobs_by_stage: dict[str, list[str]] = defaultdict(list)
    for name, config in jobs.items():
        jobs_by_stage[str(config.get("stage", "test"))].append(name)
    for index in range(1, len(stage_names)):
        for target in sorted(jobs_by_stage[stage_names[index]]):
            if target in explicit_jobs:
                continue
            for source_name in sorted(jobs_by_stage[stage_names[index - 1]]):
                relations.add((source_name, target, "stage"))
    edges = [
        {
            "id": f"{job_ids[source_name]}-before-{job_ids[target]}",
            "from": job_ids[source_name], "to": job_ids[target],
            "label": label, "kind": "dependency",
        }
        for source_name, target, label in sorted(relations)
    ]
    return {
        "version": "1",
        "diagram": {
            "title": title or f"{source_file.name} GitLab CI",
            "direction": "TB", "theme": "colorblind",
        },
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def import_source(
    path: Path, source_type: str, title: str | None = None, max_files: int = 500,
) -> dict[str, Any]:
    if source_type == "auto":
        if path.is_dir():
            terraform_count = sum(
                1 for item in path.rglob("*.tf")
                if not (set(item.relative_to(path).parts) & IGNORED_SOURCE_DIRS)
            )
            if terraform_count:
                source_type = "terraform"
            elif (path / ".github" / "workflows").is_dir():
                source_type = "github-actions"
            elif (path / ".gitlab-ci.yml").is_file() or (path / ".gitlab-ci.yaml").is_file():
                source_type = "gitlab-ci"
            else:
                python_count = sum(1 for item in path.rglob("*.py") if not (set(item.relative_to(path).parts) & IGNORED_SOURCE_DIRS))
                typescript_count = sum(
                    1 for item in path.rglob("*")
                    if item.suffix.lower() in {".ts", ".tsx", ".js", ".jsx"}
                    and not (set(item.relative_to(path).parts) & IGNORED_SOURCE_DIRS)
                )
                if python_count == typescript_count == 0:
                    raise ValueError("cannot detect source type in directory; use --type")
                source_type = "python" if python_count >= typescript_count else "typescript"
        elif path.suffix.lower() == ".tf":
            source_type = "terraform"
        elif path.suffix.lower() == ".sql":
            source_type = "sql"
        else:
            loaded = load_data(path)
            if loaded.get("apiVersion") and loaded.get("kind"):
                source_type = "kubernetes"
            elif "openapi" in loaded or "swagger" in loaded:
                source_type = "openapi"
            elif "services" in loaded:
                source_type = "compose"
            elif isinstance(loaded.get("jobs"), dict):
                source_type = "github-actions"
            elif isinstance(loaded.get("stages"), list):
                source_type = "gitlab-ci"
            else:
                raise ValueError("cannot detect source type; use --type")
    if source_type == "python":
        return import_python_tree(path, title, max_files)
    if source_type == "typescript":
        return import_typescript_tree(path, title, max_files)
    if source_type == "terraform":
        return import_terraform(path, title, max_files)
    if source_type == "kubernetes":
        return import_kubernetes(path, title, max_files)
    if source_type == "github-actions":
        return import_github_actions(path, title, max_files)
    if source_type == "gitlab-ci":
        return import_gitlab_ci(path, title, max_files)
    if source_type == "sql":
        return import_sql(path.read_text(encoding="utf-8"), title)
    loaded = load_data(path)
    if source_type == "openapi":
        return import_openapi(loaded, title)
    if source_type == "compose":
        return import_compose(loaded, title)
    raise ValueError(f"unsupported source type: {source_type}")


def semantic_pages(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if "pages" not in data:
        return {
            "main": {
                "id": "main",
                "title": str(data.get("diagram", {}).get("title", "Diagram")),
                "diagram": data.get("diagram", {}),
                "groups": data.get("groups", []),
                "nodes": data.get("nodes", []),
                "edges": data.get("edges", []),
            }
        }
    return {
        str(page["id"]): page
        for page in data.get("pages", [])
        if isinstance(page, dict) and page.get("id")
    }


def semantic_value(category: str, value: dict[str, Any]) -> dict[str, Any]:
    ignored = {
        "nodes": {"position", "size", "style"},
        "edges": {"style"},
        "groups": set(),
    }[category]
    return {
        key: copy.deepcopy(value[key])
        for key in sorted(value)
        if key not in ignored
    }


def architecture_diff(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    baseline_name: str = "baseline",
    candidate_name: str = "candidate",
) -> dict[str, Any]:
    baseline_errors = [
        item for item in validate_ir(baseline) if item["level"] == "error"
    ]
    candidate_errors = [
        item for item in validate_ir(candidate) if item["level"] == "error"
    ]
    if baseline_errors:
        raise ValueError(f"baseline is invalid: {baseline_errors[0]['message']}")
    if candidate_errors:
        raise ValueError(f"candidate is invalid: {candidate_errors[0]['message']}")
    before_pages = semantic_pages(baseline)
    after_pages = semantic_pages(candidate)
    changes: dict[str, dict[str, list[dict[str, Any]]]] = {
        category: {"added": [], "removed": [], "changed": []}
        for category in ("pages", "groups", "nodes", "edges")
    }
    before_page_ids, after_page_ids = set(before_pages), set(after_pages)
    for page_id in sorted(after_page_ids - before_page_ids):
        changes["pages"]["added"].append({
            "id": page_id, "after": {"title": str(after_pages[page_id].get("title", page_id))},
        })
    for page_id in sorted(before_page_ids - after_page_ids):
        changes["pages"]["removed"].append({
            "id": page_id, "before": {"title": str(before_pages[page_id].get("title", page_id))},
        })
    for page_id in sorted(before_page_ids & after_page_ids):
        before_title = str(before_pages[page_id].get("title", page_id))
        after_title = str(after_pages[page_id].get("title", page_id))
        if before_title != after_title:
            changes["pages"]["changed"].append({
                "id": page_id,
                "before": {"title": before_title},
                "after": {"title": after_title},
            })
    for page_id in sorted(before_page_ids | after_page_ids):
        before_page = before_pages.get(page_id, {})
        after_page = after_pages.get(page_id, {})
        for category in ("groups", "nodes", "edges"):
            before_items = {
                str(item["id"]): semantic_value(category, item)
                for item in before_page.get(category, [])
                if isinstance(item, dict) and item.get("id")
            }
            after_items = {
                str(item["id"]): semantic_value(category, item)
                for item in after_page.get(category, [])
                if isinstance(item, dict) and item.get("id")
            }
            for item_id in sorted(set(after_items) - set(before_items)):
                changes[category]["added"].append({
                    "page": page_id, "id": item_id, "after": after_items[item_id],
                })
            for item_id in sorted(set(before_items) - set(after_items)):
                changes[category]["removed"].append({
                    "page": page_id, "id": item_id, "before": before_items[item_id],
                })
            for item_id in sorted(set(before_items) & set(after_items)):
                if before_items[item_id] != after_items[item_id]:
                    changes[category]["changed"].append({
                        "page": page_id, "id": item_id,
                        "before": before_items[item_id], "after": after_items[item_id],
                    })
    summary = {
        status: sum(
            len(changes[category][status])
            for category in changes
        )
        for status in ("added", "removed", "changed")
    }
    return {
        "version": "1",
        "baseline": baseline_name,
        "candidate": candidate_name,
        "drift": any(summary.values()),
        "summary": {**summary, "total": sum(summary.values())},
        "changes": changes,
    }


DRIFT_STYLES = {
    "added": {"fill": "#d9f0d3", "stroke": "#009e73", "font": "#111111"},
    "removed": {
        "fill": "#f4cccc", "stroke": "#d55e00", "font": "#111111", "dashed": True,
    },
    "changed": {"fill": "#fff2cc", "stroke": "#a65f00", "font": "#111111"},
}
DRIFT_EDGE_STYLES = {
    "added": {"color": "#009e73", "width": 3},
    "removed": {"color": "#d55e00", "width": 3, "dashed": True},
    "changed": {"color": "#a65f00", "width": 3},
}
DRIFT_CONTEXT_STYLE = {
    "fill": "#eeeeee", "stroke": "#7a7a7a", "font": "#111111",
}
DRIFT_CONTEXT_EDGE_STYLE = {"color": "#7a7a7a", "width": 2}


def drift_diagram(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    before_pages = semantic_pages(baseline)
    after_pages = semantic_pages(candidate)
    status_by_item: dict[tuple[str, str, str], str] = {}
    for category in ("groups", "nodes", "edges"):
        for status in ("added", "removed", "changed"):
            for item in report["changes"][category][status]:
                status_by_item[(category, str(item["page"]), str(item["id"]))] = status
    pages: list[dict[str, Any]] = []
    for page_id in sorted(set(before_pages) | set(after_pages)):
        before_page = before_pages.get(page_id, {})
        after_page = after_pages.get(page_id, {})
        source_page = after_page or before_page
        before_groups = {
            str(item["id"]): item for item in before_page.get("groups", [])
            if isinstance(item, dict) and item.get("id")
        }
        after_groups = {
            str(item["id"]): item for item in after_page.get("groups", [])
            if isinstance(item, dict) and item.get("id")
        }
        groups = []
        for group_id in sorted(set(before_groups) | set(after_groups)):
            group = copy.deepcopy(
                after_groups[group_id] if group_id in after_groups else before_groups[group_id]
            )
            status = status_by_item.get(("groups", page_id, group_id))
            if status:
                group["label"] = f"{group['label']} [{status.upper()}]"
            groups.append(group)
        before_nodes = {
            str(item["id"]): item for item in before_page.get("nodes", [])
            if isinstance(item, dict) and item.get("id")
        }
        after_nodes = {
            str(item["id"]): item for item in after_page.get("nodes", [])
            if isinstance(item, dict) and item.get("id")
        }
        nodes = []
        for node_id in sorted(set(before_nodes) | set(after_nodes)):
            node = copy.deepcopy(
                after_nodes[node_id] if node_id in after_nodes else before_nodes[node_id]
            )
            status = status_by_item.get(("nodes", page_id, node_id))
            if status:
                node["style"] = {**node.get("style", {}), **DRIFT_STYLES[status]}
                description = str(node.get("description", "")).strip()
                node["description"] = f"{status.upper()} · {description}".rstrip(" ·")
            else:
                node["style"] = {
                    **node.get("style", {}), **DRIFT_CONTEXT_STYLE,
                }
            nodes.append(node)
        before_edges = {
            str(item["id"]): item for item in before_page.get("edges", [])
            if isinstance(item, dict) and item.get("id")
        }
        after_edges = {
            str(item["id"]): item for item in after_page.get("edges", [])
            if isinstance(item, dict) and item.get("id")
        }
        edges = []
        for edge_id in sorted(set(before_edges) | set(after_edges)):
            edge = copy.deepcopy(
                after_edges[edge_id] if edge_id in after_edges else before_edges[edge_id]
            )
            status = status_by_item.get(("edges", page_id, edge_id))
            if status:
                edge["style"] = {
                    **edge.get("style", {}), **DRIFT_EDGE_STYLES[status],
                }
                label = str(edge.get("label", "")).strip()
                edge["label"] = f"{status.upper()} · {label}".rstrip(" ·")
            else:
                edge["style"] = {
                    **edge.get("style", {}), **DRIFT_CONTEXT_EDGE_STYLE,
                }
            edges.append(edge)
        pages.append({
            "id": page_id,
            "title": f"Drift · {source_page.get('title', page_id)}",
            "diagram": copy.deepcopy(source_page.get("diagram", {})),
            "groups": groups,
            "nodes": nodes,
            "edges": edges,
        })
    return {
        "version": "1",
        "diagram": {
            "direction": "LR", "theme": "colorblind", "gap": 120,
        },
        "pages": pages,
    }


def validate_blueprint(data: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if str(data.get("version", "")) != "1":
        issues.append(issue("error", "blueprint.version", "version must be \"1\""))
    metadata = data.get("blueprint")
    if not isinstance(metadata, dict) or not metadata.get("title"):
        issues.append(issue("error", "blueprint.metadata", "blueprint requires a title"))
        metadata = {}
    if metadata.get("theme", "colorblind") not in ALLOWED_THEMES:
        issues.append(issue("error", "blueprint.theme", f"unknown theme: {metadata.get('theme')}"))
    if metadata.get("direction", "LR") not in ALLOWED_DIRECTIONS:
        issues.append(issue("error", "blueprint.direction", "direction must be LR or TB"))
    elements = data.get("elements")
    relations = data.get("relations", [])
    if not isinstance(elements, list) or not elements:
        return issues + [issue("error", "blueprint.elements", "elements must be a non-empty array")]
    if not isinstance(relations, list):
        return issues + [issue("error", "blueprint.relations", "relations must be an array")]
    element_ids: set[str] = set()
    element_map: dict[str, dict[str, Any]] = {}
    for index, element in enumerate(elements):
        if not isinstance(element, dict) or not element.get("id") or not element.get("label"):
            issues.append(issue("error", "blueprint.element.required", f"element {index} requires id and label"))
            continue
        element_id = str(element["id"])
        if not valid_semantic_id(element_id):
            issues.append(issue("error", "id.format", f"invalid element id: {element_id}", element_id))
        if element_id in element_ids:
            issues.append(issue("error", "id.duplicate", f"duplicate element id: {element_id}", element_id))
        element_ids.add(element_id)
        element_map[element_id] = element
        scope = element.get("scope", "component")
        if scope not in ALLOWED_BLUEPRINT_SCOPES:
            issues.append(issue("error", "blueprint.scope", f"unknown scope: {scope}", element_id))
        kind = element.get("kind")
        if kind is not None and kind not in ALLOWED_KINDS:
            issues.append(issue("error", "blueprint.kind", f"unknown kind: {kind}", element_id))
        for field in ("parent", "deploy_to"):
            target = element.get(field)
            if target is not None and not isinstance(target, str):
                issues.append(issue("error", f"blueprint.{field}", f"{field} must be an element id", element_id))
    for element_id, element in element_map.items():
        parent = element.get("parent")
        if parent and parent not in element_ids:
            issues.append(issue("error", "blueprint.parent", f"unknown parent: {parent}", element_id))
        deployment = element.get("deploy_to")
        if deployment and deployment not in element_ids:
            issues.append(issue("error", "blueprint.deploy-to", f"unknown deployment target: {deployment}", element_id))
        elif deployment and element_map[deployment].get("scope") != "infrastructure":
            issues.append(issue(
                "error", "blueprint.deploy-to",
                f"deployment target must have infrastructure scope: {deployment}", element_id,
            ))
        visited: set[str] = set()
        current = element_id
        while current in element_map and element_map[current].get("parent"):
            current = str(element_map[current]["parent"])
            if current in visited or current == element_id:
                issues.append(issue("error", "blueprint.parent-cycle", "parent hierarchy contains a cycle", element_id))
                break
            visited.add(current)
    relation_ids: set[str] = set()
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict) or not relation.get("from") or not relation.get("to"):
            issues.append(issue("error", "blueprint.relation.required", f"relation {index} requires from and to"))
            continue
        source, target = str(relation["from"]), str(relation["to"])
        relation_id = str(relation.get("id", f"{source}-to-{target}-{index + 1}"))
        if not valid_semantic_id(relation_id):
            issues.append(issue("error", "id.format", f"invalid relation id: {relation_id}", relation_id))
        if relation_id in relation_ids:
            issues.append(issue("error", "id.duplicate", f"duplicate relation id: {relation_id}", relation_id))
        if relation_id in element_ids:
            issues.append(issue("error", "id.duplicate", f"relation id conflicts with element: {relation_id}", relation_id))
        relation_ids.add(relation_id)
        if source not in element_ids:
            issues.append(issue("error", "blueprint.relation.source", f"unknown source: {source}", relation_id))
        if target not in element_ids:
            issues.append(issue("error", "blueprint.relation.target", f"unknown target: {target}", relation_id))
        if source == target:
            issues.append(issue("error", "blueprint.relation.self-loop", "self-relations are not supported", relation_id))
        if relation.get("kind", "sync") not in ALLOWED_EDGE_KINDS:
            issues.append(issue("error", "blueprint.relation.kind", "unknown relation kind", relation_id))
    decisions = data.get("decisions", [])
    if not isinstance(decisions, list):
        issues.append(issue("error", "blueprint.decisions", "decisions must be an array"))
        decisions = []
    decision_ids: set[str] = set()
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict) or not decision.get("id") or not decision.get("title"):
            issues.append(issue("error", "blueprint.decision.required", f"decision {index} requires id and title"))
            continue
        decision_id = str(decision["id"])
        if not valid_semantic_id(decision_id):
            issues.append(issue("error", "id.format", f"invalid decision id: {decision_id}", decision_id))
        if decision_id in decision_ids:
            issues.append(issue("error", "id.duplicate", f"duplicate decision id: {decision_id}", decision_id))
        decision_ids.add(decision_id)
        status = decision.get("status", "proposed")
        if status not in ALLOWED_DECISION_STATUS:
            issues.append(issue("error", "blueprint.decision.status", f"unknown status: {status}", decision_id))
        affects = decision.get("affects", [])
        if not isinstance(affects, list) or not affects:
            issues.append(issue("error", "blueprint.decision.affects", "decision requires affected elements", decision_id))
        else:
            for element_id in affects:
                if element_id not in element_ids:
                    issues.append(issue(
                        "error", "blueprint.decision.affects",
                        f"unknown affected element: {element_id}", decision_id,
                    ))
    views = data.get("views")
    if views is not None:
        if not isinstance(views, list) or not views:
            issues.append(issue("error", "blueprint.views", "views must be a non-empty array"))
        else:
            unknown = sorted(set(views) - ALLOWED_BLUEPRINT_VIEWS)
            if unknown:
                issues.append(issue("error", "blueprint.views", f"unknown views: {', '.join(unknown)}"))
    return issues


def blueprint_default_kind(element: dict[str, Any]) -> str:
    if element.get("kind"):
        return str(element["kind"])
    return {
        "actor": "client",
        "external": "external",
        "data": "database",
        "infrastructure": "external",
    }.get(str(element.get("scope", "component")), "service")


def blueprint_groups(
    elements: list[dict[str, Any]], field: str, prefix: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    labels = sorted({str(element[field]) for element in elements if element.get(field)})
    groups: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    used: set[str] = {str(element["id"]) for element in elements}
    for label in labels:
        base = f"group-{prefix}-{slugify(label)}"
        group_id = base
        suffix = 2
        while group_id in used:
            group_id = f"{base}-{suffix}"
            suffix += 1
        used.add(group_id)
        mapping[label] = group_id
        groups.append({"id": group_id, "label": label})
    return groups, mapping


def blueprint_node(
    element: dict[str, Any], group: str | None = None, link: str | None = None,
) -> dict[str, Any]:
    description_parts = [
        str(element[field]).strip()
        for field in ("description", "technology", "runtime")
        if element.get(field)
    ]
    node: dict[str, Any] = {
        "id": str(element["id"]),
        "label": str(element["label"]),
        "kind": blueprint_default_kind(element),
    }
    if description_parts:
        node["description"] = " · ".join(dict.fromkeys(description_parts))
    if group:
        node["group"] = group
    if link:
        node["link"] = link
    return node


def blueprint_project_endpoint(
    element_id: str, visible: set[str], elements: dict[str, dict[str, Any]],
) -> str | None:
    current = element_id
    visited: set[str] = set()
    while current not in visible:
        if current in visited or current not in elements or not elements[current].get("parent"):
            return None
        visited.add(current)
        current = str(elements[current]["parent"])
    return current


def blueprint_edges(
    relations: list[dict[str, Any]],
    visible: set[str],
    elements: dict[str, dict[str, Any]],
    project: bool = False,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    used_ids: set[str] = set()
    for index, relation in enumerate(relations, start=1):
        source, target = str(relation["from"]), str(relation["to"])
        if project:
            source = blueprint_project_endpoint(source, visible, elements) or ""
            target = blueprint_project_endpoint(target, visible, elements) or ""
        if not source or not target or source == target or source not in visible or target not in visible:
            continue
        label = str(relation.get("label", ""))
        kind = str(relation.get("kind", "sync"))
        key = (source, target, label, kind)
        if key in seen:
            continue
        seen.add(key)
        base_id = str(relation.get("id", f"{source}-to-{target}-{index}"))
        edge_id = base_id
        suffix = 2
        while edge_id in used_ids:
            edge_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(edge_id)
        edges.append({"id": edge_id, "from": source, "to": target, "label": label, "kind": kind})
    return edges


def blueprint_to_ir(
    data: dict[str, Any], requested_views: list[str] | None = None,
) -> dict[str, Any]:
    validation = validate_blueprint(data)
    errors = [item for item in validation if item["level"] == "error"]
    if errors:
        raise ValueError(f"invalid blueprint: {errors[0]['message']}")
    metadata = data["blueprint"]
    title = str(metadata["title"])
    theme = str(metadata.get("theme", "colorblind"))
    direction = str(metadata.get("direction", "LR"))
    element_list = [copy.deepcopy(element) for element in data["elements"]]
    elements = {str(element["id"]): element for element in element_list}
    relations = [copy.deepcopy(relation) for relation in data.get("relations", [])]
    default_views = ["context", "logical", "data", "deployment", "security"]
    if data.get("decisions"):
        default_views.append("decisions")
    views = requested_views or data.get("views") or default_views
    unknown = sorted(set(views) - ALLOWED_BLUEPRINT_VIEWS)
    if unknown:
        raise ValueError(f"unknown blueprint views: {', '.join(unknown)}")
    pages: list[dict[str, Any]] = []

    if "context" in views:
        context_elements = [
            element for element in element_list
            if element.get("scope", "component") in {"actor", "external", "system"}
        ]
        if not any(element.get("scope") == "system" for element in context_elements):
            context_elements.extend(
                element for element in element_list
                if not element.get("parent") and element not in context_elements
            )
        visible = {str(element["id"]) for element in context_elements}
        nodes = [
            blueprint_node(
                element,
                link="logical" if element.get("scope") == "system" and "logical" in views else None,
            )
            for element in context_elements
        ]
        pages.append({
            "id": "context", "title": f"{title} — System Context",
            "nodes": nodes, "edges": blueprint_edges(relations, visible, elements, project=True),
        })

    if "logical" in views:
        parent_ids = {
            str(element["parent"]) for element in element_list if element.get("parent")
        }
        logical_elements = [
            element for element in element_list
            if element.get("scope", "component") != "infrastructure"
            and not (element.get("scope") == "system" and str(element["id"]) in parent_ids)
        ]
        groups, group_map = blueprint_groups(logical_elements, "domain", "domain")
        nodes = []
        for element in logical_elements:
            link = None
            if element.get("scope") == "data" and "data" in views:
                link = "data"
            elif element.get("deploy_to") and "deployment" in views:
                link = "deployment"
            nodes.append(blueprint_node(element, group_map.get(str(element.get("domain"))), link))
        visible = {str(element["id"]) for element in logical_elements}
        pages.append({
            "id": "logical", "title": f"{title} — Logical Architecture",
            "groups": groups, "nodes": nodes,
            "edges": blueprint_edges(relations, visible, elements),
        })

    if "data" in views:
        data_ids = {
            str(element["id"]) for element in element_list
            if element.get("scope") == "data" or blueprint_default_kind(element) in {"database", "queue"}
        }
        for relation in relations:
            source, target = str(relation["from"]), str(relation["to"])
            if relation.get("kind") == "data" or source in data_ids or target in data_ids:
                data_ids.update((str(relation["from"]), str(relation["to"])))
        data_elements = [element for element in element_list if str(element["id"]) in data_ids]
        if data_elements:
            groups, group_map = blueprint_groups(data_elements, "domain", "domain")
            pages.append({
                "id": "data", "title": f"{title} — Data Flow",
                "groups": groups,
                "nodes": [
                    blueprint_node(element, group_map.get(str(element.get("domain"))))
                    for element in data_elements
                ],
                "edges": blueprint_edges(relations, data_ids, elements),
            })

    if "deployment" in views:
        deployment_elements = [
            element for element in element_list
            if element.get("scope") == "infrastructure" or element.get("deploy_to")
        ]
        if deployment_elements:
            groups, group_map = blueprint_groups(deployment_elements, "zone", "zone")
            visible = {str(element["id"]) for element in deployment_elements}
            infrastructure_ids = {
                str(element["id"]) for element in deployment_elements
                if element.get("scope") == "infrastructure"
            }
            deployment_edges = blueprint_edges(relations, infrastructure_ids, elements)
            for element in deployment_elements:
                target = element.get("deploy_to")
                if target and target in visible:
                    deployment_edges.append({
                        "id": f"deploy-{element['id']}-to-{target}",
                        "from": str(target), "to": str(element["id"]),
                        "label": "hosts", "kind": "dependency",
                    })
            pages.append({
                "id": "deployment", "title": f"{title} — Deployment",
                "diagram": {"direction": "TB"},
                "groups": groups,
                "nodes": [
                    blueprint_node(element, group_map.get(str(element.get("zone"))))
                    for element in deployment_elements
                ],
                "edges": deployment_edges,
            })

    if "security" in views:
        zoned_ids = {
            str(element["id"]) for element in element_list
            if element.get("zone") and element.get("scope") != "infrastructure"
        }
        for relation in relations:
            source, target = str(relation["from"]), str(relation["to"])
            if source in zoned_ids or target in zoned_ids:
                if elements[source].get("scope") in {"actor", "external"}:
                    zoned_ids.add(source)
                if elements[target].get("scope") in {"actor", "external"}:
                    zoned_ids.add(target)
        security_elements = [element for element in element_list if str(element["id"]) in zoned_ids]
        if security_elements:
            groups, group_map = blueprint_groups(security_elements, "zone", "zone")
            pages.append({
                "id": "security", "title": f"{title} — Network & Security Zones",
                "groups": groups,
                "nodes": [
                    blueprint_node(element, group_map.get(str(element.get("zone"))))
                    for element in security_elements
                ],
                "edges": blueprint_edges(relations, zoned_ids, elements),
            })
    if "decisions" in views and data.get("decisions"):
        owned_affected: dict[str, list[str]] = {}
        affected_owner: dict[str, str] = {}
        for decision in data["decisions"]:
            decision_id = str(decision["id"])
            owned_affected[decision_id] = []
            for element_id in decision.get("affects", []):
                element_id = str(element_id)
                if element_id not in affected_owner:
                    affected_owner[element_id] = decision_id
                    owned_affected[decision_id].append(element_id)
        affected_ids = set(affected_owner)
        decision_nodes = []
        decision_edges = []
        lane_starts: dict[str, int] = {}
        lane_cursor = 100
        for decision in data["decisions"]:
            decision_id = str(decision["id"])
            lane_starts[decision_id] = lane_cursor
            lane_cursor += max(360, len(owned_affected[decision_id]) * 260) + 100
        for decision in data["decisions"]:
            decision_id = f"decision-{decision['id']}"
            status = str(decision.get("status", "proposed"))
            summary = str(decision.get("decision") or decision.get("rationale") or "").strip()
            description = status.upper()
            if summary:
                description += f" · {summary}"
            lane_id = str(decision["id"])
            lane_width = max(360, len(owned_affected[lane_id]) * 260)
            decision_nodes.append({
                "id": decision_id,
                "label": str(decision["title"]),
                "kind": "note",
                "description": description,
                "size": {"width": 280, "height": 100},
                "position": {
                    "x": lane_starts[lane_id] + (lane_width - 280) // 2,
                    "y": 100,
                },
            })
            for element_id in decision.get("affects", []):
                decision_edges.append({
                    "id": f"{decision_id}-affects-{element_id}",
                    "from": decision_id,
                    "to": str(element_id),
                    "label": "affects",
                    "kind": "association",
                })
        affected_nodes = []
        lane_offsets: dict[str, int] = defaultdict(int)
        for element_id in sorted(
            affected_ids,
            key=lambda item: (
                list(lane_starts).index(affected_owner[item]),
                owned_affected[affected_owner[item]].index(item),
            ),
        ):
            lane_id = affected_owner[element_id]
            node = blueprint_node(
                elements[element_id],
                link=(
                    "logical"
                    if "logical" in views
                    and elements[element_id].get("scope") != "infrastructure"
                    else None
                ),
            )
            node["position"] = {
                "x": lane_starts[lane_id] + lane_offsets[lane_id] * 260,
                "y": 360,
            }
            lane_offsets[lane_id] += 1
            affected_nodes.append(node)
        pages.append({
            "id": "decisions", "title": f"{title} — Architecture Decisions",
            "diagram": {"direction": "TB"},
            "nodes": decision_nodes + affected_nodes,
            "edges": decision_edges,
        })
    if not pages:
        raise ValueError("requested blueprint views produced no pages")
    page_ids = {str(page["id"]) for page in pages}
    for page in pages:
        for node in page.get("nodes", []):
            if node.get("link") not in page_ids:
                node.pop("link", None)
    return {
        "version": "1",
        "diagram": {"direction": direction, "theme": theme},
        "pages": pages,
    }


def normalize_data_type(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", value).strip().lower())


def validate_erd(data: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if str(data.get("version", "")) != "1":
        issues.append(issue("error", "erd.version", "version must be \"1\""))
    metadata = data.get("erd")
    if not isinstance(metadata, dict) or not metadata.get("title"):
        issues.append(issue("error", "erd.metadata", "erd requires a title"))
        metadata = {}
    if metadata.get("theme", "colorblind") not in ALLOWED_THEMES:
        issues.append(issue("error", "erd.theme", f"unknown theme: {metadata.get('theme')}"))
    if metadata.get("direction", "LR") not in ALLOWED_DIRECTIONS:
        issues.append(issue("error", "erd.direction", "direction must be LR or TB"))
    entities = data.get("entities")
    relationships = data.get("relationships", [])
    if not isinstance(entities, list) or not entities:
        return issues + [issue("error", "erd.entities", "entities must be a non-empty array")]
    if not isinstance(relationships, list):
        return issues + [issue("error", "erd.relationships", "relationships must be an array")]

    entity_map: dict[str, dict[str, Any]] = {}
    field_maps: dict[str, dict[str, dict[str, Any]]] = {}
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict) or not entity.get("id") or not entity.get("label"):
            issues.append(issue("error", "erd.entity.required", f"entity {index} requires id and label"))
            continue
        entity_id = str(entity["id"])
        if not valid_semantic_id(entity_id):
            issues.append(issue("error", "id.format", f"invalid entity id: {entity_id}", entity_id))
        if entity_id in entity_map:
            issues.append(issue("error", "id.duplicate", f"duplicate entity id: {entity_id}", entity_id))
        entity_map[entity_id] = entity
        fields = entity.get("fields")
        if not isinstance(fields, list) or not fields:
            issues.append(issue("error", "erd.fields", "entity requires fields", entity_id))
            continue
        field_map: dict[str, dict[str, Any]] = {}
        for field_index, field in enumerate(fields):
            if not isinstance(field, dict) or not field.get("name") or not field.get("type"):
                issues.append(issue(
                    "error", "erd.field.required",
                    f"field {field_index} requires name and type", entity_id,
                ))
                continue
            field_name = str(field["name"])
            if field_name in field_map:
                issues.append(issue(
                    "error", "erd.field.duplicate",
                    f"duplicate field: {field_name}", entity_id,
                ))
            field_map[field_name] = field
            for flag in ("primary_key", "foreign_key", "unique", "nullable"):
                if flag in field and not isinstance(field[flag], bool):
                    issues.append(issue(
                        "error", "erd.field.flag",
                        f"{field_name}.{flag} must be boolean", entity_id,
                    ))
        field_maps[entity_id] = field_map
        if not any(field.get("primary_key") for field in field_map.values()):
            issues.append(issue("warning", "erd.primary-key", "entity has no primary key", entity_id))

    relationship_ids: set[str] = set()
    for index, relationship in enumerate(relationships):
        if (
            not isinstance(relationship, dict)
            or not relationship.get("from")
            or not relationship.get("to")
        ):
            issues.append(issue(
                "error", "erd.relationship.required",
                f"relationship {index} requires from and to",
            ))
            continue
        source, target = str(relationship["from"]), str(relationship["to"])
        relationship_id = str(
            relationship.get("id", f"{source}-to-{target}-{index + 1}")
        )
        if not valid_semantic_id(relationship_id):
            issues.append(issue("error", "id.format", f"invalid relationship id: {relationship_id}"))
        if relationship_id in relationship_ids or relationship_id in entity_map:
            issues.append(issue("error", "id.duplicate", f"duplicate id: {relationship_id}"))
        relationship_ids.add(relationship_id)
        if source not in entity_map:
            issues.append(issue("error", "erd.relationship.source", f"unknown entity: {source}", relationship_id))
        if target not in entity_map:
            issues.append(issue("error", "erd.relationship.target", f"unknown entity: {target}", relationship_id))
        for side in ("from", "to"):
            cardinality = relationship.get(f"{side}_cardinality", "one")
            if cardinality not in ALLOWED_CARDINALITIES:
                issues.append(issue(
                    "error", "erd.cardinality",
                    f"unknown {side} cardinality: {cardinality}", relationship_id,
                ))
            entity_id = source if side == "from" else target
            fields = relationship.get(f"{side}_fields", [])
            if not isinstance(fields, list):
                issues.append(issue(
                    "error", "erd.relationship.fields",
                    f"{side}_fields must be an array", relationship_id,
                ))
                continue
            for field_name in fields:
                if entity_id in field_maps and field_name not in field_maps[entity_id]:
                    issues.append(issue(
                        "error", "erd.relationship.field",
                        f"unknown field {entity_id}.{field_name}", relationship_id,
                    ))
        source_fields = relationship.get("from_fields", [])
        target_fields = relationship.get("to_fields", [])
        if len(source_fields) != len(target_fields):
            issues.append(issue(
                "error", "erd.relationship.arity",
                "from_fields and to_fields must have equal length", relationship_id,
            ))
        if source in field_maps and target in field_maps:
            for source_field, target_field in zip(source_fields, target_fields):
                if source_field in field_maps[source] and target_field in field_maps[target]:
                    source_definition = field_maps[source][source_field]
                    target_definition = field_maps[target][target_field]
                    left = normalize_data_type(str(source_definition["type"]))
                    right = normalize_data_type(str(target_definition["type"]))
                    if left != right:
                        issues.append(issue(
                            "warning", "erd.type-mismatch",
                            f"relationship types differ: {left} vs {right}", relationship_id,
                        ))
                    if not (
                        source_definition.get("primary_key")
                        or source_definition.get("unique")
                    ):
                        issues.append(issue(
                            "warning", "erd.reference-key",
                            f"referenced field is not primary or unique: {source}.{source_field}",
                            relationship_id,
                        ))
                    if not target_definition.get("foreign_key"):
                        issues.append(issue(
                            "warning", "erd.foreign-key",
                            f"relationship field is not marked as foreign key: {target}.{target_field}",
                            relationship_id,
                        ))
                    if relationship.get("identifying") and not target_definition.get("primary_key"):
                        issues.append(issue(
                            "warning", "erd.identifying-key",
                            f"identifying relationship field is not part of child primary key: {target}.{target_field}",
                            relationship_id,
                        ))
    return issues


def erd_to_ir(data: dict[str, Any]) -> dict[str, Any]:
    errors = [item for item in validate_erd(data) if item["level"] == "error"]
    if errors:
        raise ValueError(f"invalid erd: {errors[0]['message']}")
    metadata = data["erd"]
    schemas = sorted({
        str(entity["schema"]) for entity in data["entities"] if entity.get("schema")
    })
    groups = [
        {"id": f"schema-{slugify(schema)}", "label": schema}
        for schema in schemas
    ]
    group_map = {schema: f"schema-{slugify(schema)}" for schema in schemas}
    nodes = []
    for entity in data["entities"]:
        node: dict[str, Any] = {
            "id": str(entity["id"]),
            "label": str(entity["label"]),
            "kind": "entity",
            "fields": copy.deepcopy(entity["fields"]),
        }
        if entity.get("schema"):
            node["group"] = group_map[str(entity["schema"])]
        if entity.get("position"):
            node["position"] = copy.deepcopy(entity["position"])
        nodes.append(node)
    edges = []
    for index, relationship in enumerate(data.get("relationships", []), start=1):
        source, target = str(relationship["from"]), str(relationship["to"])
        edges.append({
            "id": str(relationship.get("id", f"{source}-to-{target}-{index}")),
            "from": source,
            "to": target,
            "label": str(relationship.get("label", "")),
            "kind": "association",
            "style": {
                "start_cardinality": str(relationship.get("from_cardinality", "one")),
                "end_cardinality": str(relationship.get("to_cardinality", "one")),
                "dashed": not bool(relationship.get("identifying", False)),
            },
        })
    return {
        "version": "1",
        "diagram": {
            "title": str(metadata["title"]),
            "direction": str(metadata.get("direction", "LR")),
            "theme": str(metadata.get("theme", "colorblind")),
            "gap": int(metadata.get("gap", 120)),
        },
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
    }


def sql_to_erd(text: str, title: str = "Database ERD") -> dict[str, Any]:
    text = re.sub(r"--[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    table_pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[\]\w.]+)\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    entities: dict[str, dict[str, Any]] = {}
    pending_fks: list[dict[str, Any]] = []
    for match in table_pattern.finditer(text):
        raw_table = normalize_sql_name(match.group(1))
        entity_id = slugify(raw_table)
        fields: list[dict[str, Any]] = []
        field_map: dict[str, dict[str, Any]] = {}
        table_primary_keys: set[str] = set()
        for definition in split_sql_columns(match.group(2)):
            table_pk = re.match(
                r"(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)",
                definition, re.IGNORECASE,
            )
            table_fk = re.match(
                r"(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s+"
                r"REFERENCES\s+([`\"\[\]\w.]+)(?:\s*\(([^)]+)\))?",
                definition, re.IGNORECASE,
            )
            if table_pk:
                table_primary_keys.update(
                    normalize_sql_name(item) for item in table_pk.group(1).split(",")
                )
                continue
            if table_fk:
                local_fields = [
                    normalize_sql_name(item) for item in table_fk.group(1).split(",")
                ]
                remote_fields = [
                    normalize_sql_name(item)
                    for item in (table_fk.group(3) or "id").split(",")
                ]
                pending_fks.append({
                    "child": entity_id,
                    "parent_label": normalize_sql_name(table_fk.group(2)),
                    "local_fields": local_fields,
                    "remote_fields": remote_fields,
                })
                continue
            if re.match(r"(?:CONSTRAINT|UNIQUE|CHECK|EXCLUDE)\b", definition, re.I):
                continue
            column = re.match(r"([`\"\[\]\w]+)\s+(.+)", definition, re.IGNORECASE | re.DOTALL)
            if not column:
                continue
            field_name = normalize_sql_name(column.group(1))
            remainder = re.sub(r"\s+", " ", column.group(2).strip())
            type_match = re.match(
                r"(.+?)(?=\s+(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|DEFAULT|"
                r"REFERENCES|CHECK|COLLATE|CONSTRAINT|GENERATED)\b|$)",
                remainder, re.IGNORECASE,
            )
            data_type = (type_match.group(1) if type_match else remainder).strip()
            field = {
                "name": field_name,
                "type": data_type,
                "nullable": not bool(re.search(r"\bNOT\s+NULL\b|\bPRIMARY\s+KEY\b", remainder, re.I)),
                "primary_key": bool(re.search(r"\bPRIMARY\s+KEY\b", remainder, re.I)),
                "unique": bool(re.search(r"\bUNIQUE\b", remainder, re.I)),
            }
            default_match = re.search(
                r"\bDEFAULT\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|"
                r"REFERENCES|CHECK|COLLATE|CONSTRAINT|GENERATED)\b|$)",
                remainder, re.IGNORECASE,
            )
            if default_match:
                field["default"] = default_match.group(1).strip()
            inline_fk = re.search(
                r"\bREFERENCES\s+([`\"\[\]\w.]+)(?:\s*\(([^)]+)\))?",
                remainder, re.IGNORECASE,
            )
            if inline_fk:
                field["foreign_key"] = True
                pending_fks.append({
                    "child": entity_id,
                    "parent_label": normalize_sql_name(inline_fk.group(1)),
                    "local_fields": [field_name],
                    "remote_fields": [
                        normalize_sql_name(item)
                        for item in (inline_fk.group(2) or "id").split(",")
                    ],
                })
            fields.append(field)
            field_map[field_name] = field
        for field_name in table_primary_keys:
            if field_name in field_map:
                field_map[field_name]["primary_key"] = True
                field_map[field_name]["nullable"] = False
        entities[raw_table] = {
            "id": entity_id,
            "label": raw_table,
            "fields": fields,
        }
    alter_fk_pattern = re.compile(
        r"ALTER\s+TABLE\s+(?:ONLY\s+)?([`\"\[\]\w.]+)\s+ADD\s+"
        r"(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s+"
        r"REFERENCES\s+([`\"\[\]\w.]+)(?:\s*\(([^)]+)\))?\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    for match in alter_fk_pattern.finditer(text):
        child_label = normalize_sql_name(match.group(1))
        pending_fks.append({
            "child": slugify(child_label),
            "parent_label": normalize_sql_name(match.group(3)),
            "local_fields": [
                normalize_sql_name(item) for item in match.group(2).split(",")
            ],
            "remote_fields": [
                normalize_sql_name(item)
                for item in (match.group(4) or "id").split(",")
            ],
        })
    if not entities:
        raise ValueError("no CREATE TABLE statements found")
    label_to_id = {label: entity["id"] for label, entity in entities.items()}
    entity_by_id = {entity["id"]: entity for entity in entities.values()}
    relationships = []
    for index, foreign_key in enumerate(pending_fks, start=1):
        parent = label_to_id.get(str(foreign_key["parent_label"]))
        child = str(foreign_key["child"])
        if not parent or child not in entity_by_id:
            continue
        for field_name in foreign_key["local_fields"]:
            for field in entity_by_id[child]["fields"]:
                if field["name"] == field_name:
                    field["foreign_key"] = True
        relationships.append({
            "id": f"fk-{parent}-{child}-{index}",
            "from": parent,
            "to": child,
            "from_fields": foreign_key["remote_fields"],
            "to_fields": foreign_key["local_fields"],
            "from_cardinality": "one",
            "to_cardinality": "zero-or-many",
            "label": "references",
        })
    return {
        "version": "1",
        "erd": {"title": title, "direction": "LR", "theme": "colorblind"},
        "entities": [entities[name] for name in sorted(entities)],
        "relationships": relationships,
    }


def validate_ha(data: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if str(data.get("version", "")) != "1":
        issues.append(issue("error", "ha.version", "version must be \"1\""))
    metadata = data.get("ha")
    if not isinstance(metadata, dict) or not metadata.get("title"):
        issues.append(issue("error", "ha.metadata", "ha requires a title"))
        metadata = {}
    if metadata.get("theme", "colorblind") not in ALLOWED_THEMES:
        issues.append(issue("error", "ha.theme", f"unknown theme: {metadata.get('theme')}"))
    for objective in ("availability", "rto", "rpo"):
        if not metadata.get(objective):
            issues.append(issue(
                "warning", f"ha.{objective}",
                f"HA model should define a measurable {objective.upper()} objective",
            ))
    domains = data.get("domains")
    components = data.get("components")
    links = data.get("links", [])
    failovers = data.get("failovers", [])
    if not isinstance(domains, list) or not domains:
        return issues + [issue("error", "ha.domains", "domains must be a non-empty array")]
    if not isinstance(components, list) or not components:
        return issues + [issue("error", "ha.components", "components must be a non-empty array")]
    if not isinstance(links, list) or not isinstance(failovers, list):
        return issues + [issue("error", "ha.collections", "links and failovers must be arrays")]

    domain_map: dict[str, dict[str, Any]] = {}
    for index, domain in enumerate(domains):
        if not isinstance(domain, dict) or not domain.get("id") or not domain.get("label"):
            issues.append(issue("error", "ha.domain.required", f"domain {index} requires id and label"))
            continue
        domain_id = str(domain["id"])
        if not valid_semantic_id(domain_id):
            issues.append(issue("error", "id.format", f"invalid domain id: {domain_id}", domain_id))
        if domain_id in domain_map:
            issues.append(issue("error", "id.duplicate", f"duplicate domain id: {domain_id}", domain_id))
        domain_map[domain_id] = domain
        if domain.get("level", "zone") not in ALLOWED_FAILURE_DOMAIN_LEVELS:
            issues.append(issue("error", "ha.domain.level", f"unknown domain level: {domain.get('level')}", domain_id))
    failure_domains = [
        domain for domain in domain_map.values() if domain.get("failure_domain", True)
    ]
    if len(failure_domains) < 2:
        issues.append(issue("warning", "ha.failure-domains", "HA design has fewer than two failure domains"))

    component_map: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        if not isinstance(component, dict) or not component.get("id") or not component.get("label"):
            issues.append(issue("error", "ha.component.required", f"component {index} requires id and label"))
            continue
        component_id = str(component["id"])
        if not valid_semantic_id(component_id):
            issues.append(issue("error", "id.format", f"invalid component id: {component_id}", component_id))
        if component_id in component_map or component_id in domain_map:
            issues.append(issue("error", "id.duplicate", f"duplicate id: {component_id}", component_id))
        component_map[component_id] = component
        if component.get("domain") not in domain_map:
            issues.append(issue("error", "ha.component.domain", f"unknown domain: {component.get('domain')}", component_id))
        role = component.get("role", "active")
        if role not in ALLOWED_HA_ROLES:
            issues.append(issue("error", "ha.component.role", f"unknown role: {role}", component_id))
        replicas = component.get("replicas", 1)
        if not isinstance(replicas, int) or isinstance(replicas, bool) or replicas < 1:
            issues.append(issue("error", "ha.component.replicas", "replicas must be a positive integer", component_id))
        elif role in {"active-active", "load-balancer"} and replicas < 2:
            issues.append(issue("warning", "ha.replica-count", f"{role} should have at least two replicas", component_id))
        elif role == "quorum" and (replicas < 3 or replicas % 2 == 0):
            issues.append(issue("warning", "ha.quorum", "quorum replicas should be odd and at least three", component_id))

    link_ids: set[str] = set()
    replicated_components: set[str] = set()
    replication_pairs: set[frozenset[str]] = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict) or not link.get("from") or not link.get("to"):
            issues.append(issue("error", "ha.link.required", f"link {index} requires from and to"))
            continue
        source, target = str(link["from"]), str(link["to"])
        link_id = str(link.get("id", f"{source}-to-{target}-{index + 1}"))
        if not valid_semantic_id(link_id):
            issues.append(issue("error", "id.format", f"invalid link id: {link_id}", link_id))
        if link_id in link_ids or link_id in component_map or link_id in domain_map:
            issues.append(issue("error", "id.duplicate", f"duplicate id: {link_id}", link_id))
        link_ids.add(link_id)
        if source not in component_map:
            issues.append(issue("error", "ha.link.source", f"unknown component: {source}", link_id))
        if target not in component_map:
            issues.append(issue("error", "ha.link.target", f"unknown component: {target}", link_id))
        mode = link.get("mode", "traffic")
        if mode not in ALLOWED_HA_LINK_MODES:
            issues.append(issue("error", "ha.link.mode", f"unknown link mode: {mode}", link_id))
        if mode in {"sync-replication", "async-replication"}:
            replicated_components.update((source, target))
            replication_pairs.add(frozenset((source, target)))
        if (
            mode == "sync-replication"
            and source in component_map
            and target in component_map
        ):
            source_domain = domain_map.get(str(component_map[source].get("domain")), {})
            target_domain = domain_map.get(str(component_map[target].get("domain")), {})
            if (
                source_domain.get("region")
                and target_domain.get("region")
                and source_domain["region"] != target_domain["region"]
            ):
                issues.append(issue(
                    "warning", "ha.cross-region-sync",
                    "synchronous replication spans regions; verify latency budget", link_id,
                ))
    for component_id, component in component_map.items():
        if component.get("stateful") and component_id not in replicated_components:
            issues.append(issue(
                "warning", "ha.stateful-replication",
                "stateful component has no replication link", component_id,
            ))

    failover_ids: set[str] = set()
    for index, failover in enumerate(failovers):
        if (
            not isinstance(failover, dict)
            or not failover.get("id")
            or not failover.get("from")
            or not failover.get("to")
            or not failover.get("trigger")
        ):
            issues.append(issue(
                "error", "ha.failover.required",
                f"failover {index} requires id, from, to, and trigger",
            ))
            continue
        failover_id = str(failover["id"])
        if not valid_semantic_id(failover_id):
            issues.append(issue("error", "id.format", f"invalid failover id: {failover_id}", failover_id))
        if failover_id in failover_ids:
            issues.append(issue("error", "id.duplicate", f"duplicate failover id: {failover_id}", failover_id))
        failover_ids.add(failover_id)
        source, target = str(failover["from"]), str(failover["to"])
        if source not in component_map:
            issues.append(issue("error", "ha.failover.source", f"unknown component: {source}", failover_id))
        if target not in component_map:
            issues.append(issue("error", "ha.failover.target", f"unknown component: {target}", failover_id))
        if source in component_map and target in component_map:
            source_domain = component_map[source].get("domain")
            target_domain = component_map[target].get("domain")
            if source_domain == target_domain:
                issues.append(issue(
                    "error", "ha.failover.domain",
                    "failover target must be in a different failure domain", failover_id,
                ))
            if component_map[target].get("role", "active") not in {
                "standby", "replica", "active-active", "active",
            }:
                issues.append(issue(
                    "warning", "ha.failover-target",
                    f"target role is not promotable: {component_map[target].get('role')}",
                    target,
                ))
            if failover.get("automatic", True) and not component_map[source].get("health_check"):
                issues.append(issue(
                    "warning", "ha.health-check",
                    "automatic failover source has no health check", source,
                ))
            if (
                (component_map[source].get("stateful") or component_map[target].get("stateful"))
                and frozenset((source, target)) not in replication_pairs
            ):
                issues.append(issue(
                    "warning", "ha.failover-replication",
                    "stateful failover pair has no direct replication link", failover_id,
                ))
    return issues


def ha_component_node(component: dict[str, Any], group: str | None = None) -> dict[str, Any]:
    role = str(component.get("role", "active"))
    replicas = int(component.get("replicas", 1))
    details = [role]
    if replicas > 1:
        details.append(f"{replicas} replicas")
    for field in ("technology", "health_check"):
        if component.get(field):
            details.append(str(component[field]))
    kind = str(component.get("kind", "service"))
    if kind not in ALLOWED_KINDS:
        kind = "process" if role == "load-balancer" else "service"
    node: dict[str, Any] = {
        "id": str(component["id"]),
        "label": str(component["label"]),
        "kind": kind,
        "description": " · ".join(details),
    }
    if group:
        node["group"] = group
    if component.get("position"):
        node["position"] = copy.deepcopy(component["position"])
    return node


def ha_to_ir(data: dict[str, Any]) -> dict[str, Any]:
    errors = [item for item in validate_ha(data) if item["level"] == "error"]
    if errors:
        raise ValueError(f"invalid ha model: {errors[0]['message']}")
    metadata = data["ha"]
    domains = {str(domain["id"]): domain for domain in data["domains"]}
    components = {str(component["id"]): component for component in data["components"]}
    group_ids = {domain_id: f"domain-{domain_id}" for domain_id in domains}
    topology_groups = [
        {"id": group_ids[domain_id], "label": str(domain["label"])}
        for domain_id, domain in domains.items()
    ]
    topology_nodes = [
        ha_component_node(component, group_ids[str(component["domain"])])
        for component in data["components"]
    ]
    mode_mapping = {
        "traffic": "sync",
        "sync-replication": "data",
        "async-replication": "async",
        "heartbeat": "association",
        "quorum": "dependency",
    }
    topology_edges = [
        {
            "id": str(link.get("id", f"{link['from']}-to-{link['to']}-{index}")),
            "from": str(link["from"]),
            "to": str(link["to"]),
            "label": str(link.get("label") or str(link.get("mode", "traffic")).replace("-", " ")),
            "kind": mode_mapping[str(link.get("mode", "traffic"))],
        }
        for index, link in enumerate(data.get("links", []), start=1)
    ]
    objectives = " · ".join(
        value for value in (
            f"Availability {metadata.get('availability')}" if metadata.get("availability") else "",
            f"RTO {metadata.get('rto')}" if metadata.get("rto") else "",
            f"RPO {metadata.get('rpo')}" if metadata.get("rpo") else "",
        ) if value
    )
    if objectives:
        topology_nodes.append({
            "id": "availability-objectives",
            "label": "Availability objectives",
            "kind": "note",
            "description": objectives,
            "position": {"x": 400, "y": 480},
            "size": {"width": 280, "height": 72},
        })

    failover_groups = []
    failover_nodes = []
    failover_edges = []
    lane_cursor = 100
    for failover in data.get("failovers", []):
        failover_id = str(failover["id"])
        group_id = f"scenario-{failover_id}"
        source = components[str(failover["from"])]
        target = components[str(failover["to"])]
        failover_groups.append({
            "id": group_id,
            "label": f"{failover['trigger']} · {'automatic' if failover.get('automatic', True) else 'manual'}",
        })
        detector_id = f"fo-{failover_id}-detector"
        source_id = f"fo-{failover_id}-source"
        target_id = f"fo-{failover_id}-target"
        objective = " · ".join(
            value for value in (
                f"RTO {failover.get('rto') or metadata.get('rto')}" if failover.get("rto") or metadata.get("rto") else "",
                f"RPO {failover.get('rpo') or metadata.get('rpo')}" if failover.get("rpo") or metadata.get("rpo") else "",
            ) if value
        )
        failover_nodes.extend([
            {
                "id": detector_id,
                "label": "Failure detector",
                "kind": "decision",
                "group": group_id,
                "description": str(source.get("health_check", "health signal")),
                "position": {"x": lane_cursor + 170, "y": 100},
            },
            {
                **ha_component_node(source, group_id),
                "id": source_id,
                "position": {"x": lane_cursor, "y": 360},
            },
            {
                **ha_component_node(target, group_id),
                "id": target_id,
                "position": {"x": lane_cursor + 380, "y": 360},
            },
        ])
        failover_edges.extend([
            {
                "id": f"{failover_id}-detect",
                "from": detector_id,
                "to": source_id,
                "label": "detect outage",
                "kind": "association",
            },
            {
                "id": f"{failover_id}-promote",
                "from": detector_id,
                "to": target_id,
                "label": f"promote {objective}".strip(),
                "kind": "async",
            },
            {
                "id": f"{failover_id}-replication",
                "from": source_id,
                "to": target_id,
                "label": str(failover.get("replication", "replicated state")),
                "kind": "data",
            },
        ])
        lane_cursor += 860
    pages = [{
        "id": "topology",
        "title": f"{metadata['title']} — HA Topology",
        "groups": topology_groups,
        "nodes": topology_nodes,
        "edges": topology_edges,
    }]
    if failover_nodes:
        pages.append({
            "id": "failover",
            "title": f"{metadata['title']} — Failover Scenarios",
            "diagram": {"direction": "TB"},
            "groups": failover_groups,
            "nodes": failover_nodes,
            "edges": failover_edges,
        })
    return {
        "version": "1",
        "diagram": {
            "direction": str(metadata.get("direction", "LR")),
            "theme": str(metadata.get("theme", "colorblind")),
            "gap": int(metadata.get("gap", 120)),
        },
        "pages": pages,
    }


def patch_target(data: dict[str, Any], page_id: str | None) -> dict[str, Any]:
    if "pages" not in data:
        if page_id:
            raise ValueError("page selector is only valid for multi-page IR")
        return data
    if not page_id:
        raise ValueError("each operation on multi-page IR requires a page")
    for page in data.get("pages", []):
        if isinstance(page, dict) and page.get("id") == page_id:
            return page
    raise ValueError(f"unknown page: {page_id}")


def find_by_id(items: list[dict[str, Any]], item_id: str, kind: str) -> dict[str, Any]:
    for item in items:
        if str(item.get("id")) == item_id:
            return item
    raise ValueError(f"unknown {kind}: {item_id}")


def apply_ir_operations(data: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    result = copy.deepcopy(data)
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict) or not operation.get("op"):
            raise ValueError(f"operation {index} requires op")
        op = str(operation["op"])
        target = patch_target(result, operation.get("page"))
        target.setdefault("groups", [])
        target.setdefault("nodes", [])
        target.setdefault("edges", [])
        nodes, edges, groups = target["nodes"], target["edges"], target["groups"]
        if op == "set-diagram":
            updates = operation.get("set")
            if not isinstance(updates, dict):
                raise ValueError("set-diagram requires set object")
            target.setdefault("diagram", {}).update(updates)
        elif op == "add-group":
            group = operation.get("group")
            if not isinstance(group, dict):
                raise ValueError("add-group requires group object")
            groups.append(copy.deepcopy(group))
        elif op == "remove-group":
            group_id = str(operation.get("id", ""))
            if any(node.get("group") == group_id for node in nodes):
                raise ValueError(f"group {group_id} is still in use")
            groups.remove(find_by_id(groups, group_id, "group"))
        elif op == "add-node":
            node = operation.get("node")
            if not isinstance(node, dict):
                raise ValueError("add-node requires node object")
            nodes.append(copy.deepcopy(node))
        elif op in {"update-node", "move-node"}:
            node = find_by_id(nodes, str(operation.get("id", "")), "node")
            updates = operation.get("set") if op == "update-node" else {"position": operation.get("position")}
            if not isinstance(updates, dict) or "id" in updates:
                raise ValueError(f"{op} requires safe mutable fields")
            node.update(copy.deepcopy(updates))
        elif op == "remove-node":
            node_id = str(operation.get("id", ""))
            incident = [edge for edge in edges if edge.get("from") == node_id or edge.get("to") == node_id]
            if incident and not operation.get("cascade"):
                raise ValueError(f"node {node_id} has {len(incident)} incident edges; set cascade=true")
            nodes.remove(find_by_id(nodes, node_id, "node"))
            if incident:
                target["edges"] = [edge for edge in edges if edge not in incident]
        elif op == "add-edge":
            edge = operation.get("edge")
            if not isinstance(edge, dict):
                raise ValueError("add-edge requires edge object")
            edges.append(copy.deepcopy(edge))
        elif op == "update-edge":
            edge = find_by_id(edges, str(operation.get("id", "")), "edge")
            updates = operation.get("set")
            if not isinstance(updates, dict) or "id" in updates:
                raise ValueError("update-edge requires safe mutable fields")
            edge.update(copy.deepcopy(updates))
        elif op == "remove-edge":
            edges.remove(find_by_id(edges, str(operation.get("id", "")), "edge"))
        else:
            raise ValueError(f"unsupported operation: {op}")
    issues = validate_ir(result)
    errors = [item for item in issues if item["level"] == "error"]
    if errors:
        raise ValueError(f"patch would create invalid IR: {errors[0]['message']}")
    return result


def drawio_candidates(
    platform_name: str | None = None,
    os_name: str | None = None,
    environ: dict[str, str] | None = None,
) -> list[str]:
    platform_name = platform_name or sys.platform
    os_name = os_name or os.name
    environ = environ or dict(os.environ)
    candidates = ["drawio", "draw.io"]
    if platform_name == "darwin":
        candidates.extend([
            "/Applications/draw.io.app/Contents/MacOS/draw.io",
            str(Path.home() / "Applications/draw.io.app/Contents/MacOS/draw.io"),
        ])
    elif os_name == "nt":
        candidates.append(r"C:\Program Files\draw.io\draw.io.exe")
        local_app_data = environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(str(Path(local_app_data) / "Programs/draw.io/draw.io.exe"))
    else:
        candidates.extend(["/usr/bin/drawio", "/snap/bin/drawio"])
    return candidates


def find_drawio(explicit: str | None = None) -> str | None:
    override = explicit or os.environ.get("DRAWIO_DESKTOP_BINARY")
    candidates = [override] if override else drawio_candidates()
    for candidate in candidates:
        if not candidate:
            continue
        if (
            os.path.isabs(candidate)
            and os.path.isfile(candidate)
            and (os.name == "nt" or os.access(candidate, os.X_OK))
        ):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:^|[-_])(password|passwd|secret|token|api[-_]?key|private[-_]?key|"
    r"client[-_]?secret|access[-_]?key|authorization)(?:$|[-_])",
    re.IGNORECASE,
)
PLACEHOLDER_SECRET_PATTERN = re.compile(
    r"^(?:|redacted|masked|example|sample|changeme|replace[-_ ]?me|"
    r"\*+|<[^>]+>|\$\{[^}]+\})$",
    re.IGNORECASE,
)
UNSAFE_LINK_SCHEMES = {"javascript", "vbscript", "file"}
INLINE_SECRET_PATTERN = re.compile(
    r"(?:password|passwd|secret|token|api[-_]?key|client[-_]?secret)"
    r"\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)
KNOWN_SECRET_PATTERN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,})"
)


def security_finding(
    level: str,
    code: str,
    message: str,
    location: str,
) -> dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        "location": location,
    }


def scan_security_value(
    value: Any,
    location: str = "$",
    key_name: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    findings: list[dict[str, Any]] = []
    external_links: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            child_location = f"{location}.{key}"
            child_findings, child_links = scan_security_value(
                value[key], child_location, str(key),
            )
            findings.extend(child_findings)
            external_links.extend(child_links)
        return findings, external_links
    if isinstance(value, list):
        for index, child in enumerate(value):
            child_findings, child_links = scan_security_value(
                child, f"{location}[{index}]", key_name,
            )
            findings.extend(child_findings)
            external_links.extend(child_links)
        return findings, external_links
    if not isinstance(value, str):
        return findings, external_links

    stripped = value.strip()
    if (
        key_name
        and SENSITIVE_KEY_PATTERN.search(key_name)
        and stripped
        and not PLACEHOLDER_SECRET_PATTERN.fullmatch(stripped)
    ):
        findings.append(security_finding(
            "error",
            "security.embedded-secret",
            f"possible credential value stored in sensitive field {key_name}",
            location,
        ))
    if "-----BEGIN " in stripped and "PRIVATE KEY-----" in stripped:
        findings.append(security_finding(
            "error",
            "security.private-key",
            "embedded private key material is prohibited",
            location,
        ))
    inline_match = INLINE_SECRET_PATTERN.search(stripped)
    if inline_match and not PLACEHOLDER_SECRET_PATTERN.fullmatch(inline_match.group(1)):
        findings.append(security_finding(
            "error",
            "security.inline-secret",
            "possible inline credential assignment is prohibited",
            location,
        ))
    if KNOWN_SECRET_PATTERN.search(stripped):
        findings.append(security_finding(
            "error",
            "security.credential-pattern",
            "value matches a known credential pattern",
            location,
        ))
    if key_name and key_name.lower() in {"link", "url", "href"}:
        parsed = urllib.parse.urlparse(stripped)
        scheme = parsed.scheme.lower()
        if scheme in UNSAFE_LINK_SCHEMES:
            findings.append(security_finding(
                "error",
                "security.unsafe-link",
                f"unsafe link scheme: {scheme}",
                location,
            ))
        elif scheme in {"http", "https", "mailto"}:
            external_links.append({"location": location, "url": stripped})
    return findings, external_links


def security_report_for_data(data: dict[str, Any], source: str) -> dict[str, Any]:
    findings, external_links = scan_security_value(data)
    return {
        "format": "drawio-security-report/v1",
        "source": source,
        "passed": not any(item["level"] == "error" for item in findings),
        "errors": sum(1 for item in findings if item["level"] == "error"),
        "warnings": sum(1 for item in findings if item["level"] == "warning"),
        "findings": findings,
        "external_links": external_links,
        "limits": {
            "structured_input_bytes": MAX_STRUCTURED_INPUT_BYTES,
            "xml_input_bytes": MAX_XML_INPUT_BYTES,
            "decompressed_page_bytes": MAX_DECOMPRESSED_PAGE_BYTES,
        },
    }


def security_report_for_drawio(path: Path) -> dict[str, Any]:
    root = load_drawio_root(path)
    values = []
    pages = []
    for diagram, _ in drawio_page_models(path):
        if diagram is None:
            continue
        page: dict[str, Any] = {
            "id": diagram.get("id", ""),
            "name": diagram.get("name", ""),
        }
        for key, value in diagram.attrib.items():
            if key.startswith("data-"):
                try:
                    page[key] = json.loads(value)
                except json.JSONDecodeError:
                    page[key] = value
        pages.append(page)
    for cell in root.findall(".//mxCell"):
        value: dict[str, Any] = {
            "id": cell.get("id", ""),
            "value": cell.get("value", ""),
            "link": cell.get("link", ""),
        }
        for key, metadata in cell.attrib.items():
            if key.startswith("data-"):
                try:
                    value[key] = json.loads(metadata)
                except json.JSONDecodeError:
                    value[key] = metadata
        values.append(value)
    return security_report_for_data({"pages": pages, "cells": values}, str(path))


def security_report_for_path(path: Path) -> dict[str, Any]:
    if path.is_dir():
        manifest = path / "bundle.json"
        diagram_ir = path / "diagram.json"
        if not manifest.is_file() or not diagram_ir.is_file():
            raise ValueError("security directory input must be a drawio-diagram bundle")
        reports = [
            security_report_for_data(load_data(manifest), str(manifest)),
            security_report_for_data(load_data(diagram_ir), str(diagram_ir)),
        ]
        drawio_files = sorted(path.glob("*.drawio"))
        reports.extend(security_report_for_drawio(item) for item in drawio_files)
        findings = [item for report in reports for item in report["findings"]]
        links = [item for report in reports for item in report["external_links"]]
        return {
            "format": "drawio-security-report/v1",
            "source": str(path),
            "passed": not any(item["level"] == "error" for item in findings),
            "errors": sum(1 for item in findings if item["level"] == "error"),
            "warnings": sum(1 for item in findings if item["level"] == "warning"),
            "findings": findings,
            "external_links": links,
            "scanned": [report["source"] for report in reports],
            "limits": reports[0]["limits"],
        }
    if path.suffix.lower() == ".drawio":
        return security_report_for_drawio(path)
    return security_report_for_data(load_data(path), str(path))


def command_security(args: argparse.Namespace) -> int:
    report = security_report_for_path(Path(args.input))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["errors"]:
        return 2
    if args.strict and report["warnings"]:
        return 3
    return 0


LEGACY_NODE_KIND_MAP = {
    "api": "service",
    "app": "service",
    "broker": "queue",
    "db": "database",
    "user": "client",
}


def rename_legacy_field(
    target: dict[str, Any],
    old: str,
    new: str,
    location: str,
    changes: list[dict[str, str]],
) -> None:
    if old not in target:
        return
    if new in target:
        raise ValueError(f"legacy field conflict at {location}: both {old} and {new} are present")
    target[new] = target.pop(old)
    changes.append({
        "location": location,
        "operation": "rename",
        "from": old,
        "to": new,
    })


def migrate_diagram_ir(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(data)
    if any(key in result for key in ("blueprint", "erd", "ha")):
        raise ValueError("migrate currently accepts Diagram IR, not Blueprint, ERD, or HA models")
    if not any(
        key in result
        for key in ("diagram", "layout", "nodes", "components", "pages", "edges", "connections")
    ):
        raise ValueError("input is not recognized as Diagram IR")
    original_version = result.get("version")
    if original_version is not None and str(original_version) not in {"0", "1"}:
        raise ValueError(f"unsupported Diagram IR version: {original_version}")
    changes: list[dict[str, str]] = []
    if str(original_version or "0") == "0":
        rename_legacy_field(result, "layout", "diagram", "$", changes)
        rename_legacy_field(result, "components", "nodes", "$", changes)
        rename_legacy_field(result, "connections", "edges", "$", changes)
        diagram = result.setdefault("diagram", {})
        if not isinstance(diagram, dict):
            raise ValueError("legacy diagram/layout must be an object")
        for field in ("title", "direction", "theme", "gap", "background"):
            if field in result:
                if field in diagram:
                    raise ValueError(f"legacy field conflict: {field} exists at root and in diagram")
                diagram[field] = result.pop(field)
                changes.append({
                    "location": "$",
                    "operation": "move",
                    "from": field,
                    "to": f"diagram.{field}",
                })
        if "pages" not in result:
            result.setdefault("groups", [])
            result.setdefault("nodes", [])
            result.setdefault("edges", [])

        for index, node in enumerate(result.get("nodes", [])):
            if not isinstance(node, dict):
                continue
            location = f"$.nodes[{index}]"
            rename_legacy_field(node, "type", "kind", location, changes)
            rename_legacy_field(node, "container", "group", location, changes)
            kind = str(node.get("kind", "service"))
            if kind in LEGACY_NODE_KIND_MAP:
                node["kind"] = LEGACY_NODE_KIND_MAP[kind]
                changes.append({
                    "location": location,
                    "operation": "map",
                    "from": kind,
                    "to": str(node["kind"]),
                })
        used_edge_ids: set[str] = set()
        for index, edge in enumerate(result.get("edges", [])):
            if not isinstance(edge, dict):
                continue
            location = f"$.edges[{index}]"
            rename_legacy_field(edge, "source", "from", location, changes)
            rename_legacy_field(edge, "target", "to", location, changes)
            rename_legacy_field(edge, "type", "kind", location, changes)
            if not edge.get("id") and edge.get("from") and edge.get("to"):
                base = slugify(f"{edge['from']}-to-{edge['to']}")
                edge_id = base
                suffix = 2
                while edge_id in used_edge_ids:
                    edge_id = f"{base}-{suffix}"
                    suffix += 1
                edge["id"] = edge_id
                changes.append({
                    "location": location,
                    "operation": "add",
                    "from": "",
                    "to": f"id={edge_id}",
                })
            if edge.get("id"):
                used_edge_ids.add(str(edge["id"]))
    if result.get("version") != IR_VERSION:
        result["version"] = IR_VERSION
        changes.append({
            "location": "$.version",
            "operation": "set",
            "from": "" if original_version is None else str(original_version),
            "to": IR_VERSION,
        })
    issues = validate_ir(result)
    report = {
        "format": "drawio-migration-report/v1",
        "from_version": "legacy-unversioned" if original_version is None else str(original_version),
        "to_version": IR_VERSION,
        "changes_required": bool(changes),
        "changes": changes,
        "score": score_issues(issues),
        "issues": issues,
    }
    return result, report


def command_migrate(args: argparse.Namespace) -> int:
    source = Path(args.input)
    result, report = migrate_diagram_ir(load_data(source))
    if not args.check:
        if not args.output:
            raise ValueError("migrate requires -o/--output unless --check is used")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report["output"] = str(output)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if any(item["level"] == "error" for item in report["issues"]):
        return 2
    if args.check and report["changes_required"]:
        return 6
    return 0


STARTER_PROFILES = {
    "architecture": ("example.architecture.json", "architecture.json"),
    "blueprint": ("example.blueprint.json", "architecture-blueprint.json"),
    "erd": ("example.erd.json", "database-erd.json"),
    "ha": ("example.ha.json", "high-availability.json"),
    "routing": ("example.routing.json", "routed-architecture.json"),
    "terraform": ("example.terraform.tf", "infrastructure.tf"),
    "kubernetes": ("example.kubernetes.json", "kubernetes.json"),
    "github-actions": ("example.github-actions.json", "github-actions.json"),
    "gitlab-ci": ("example.gitlab-ci.json", "gitlab-ci.json"),
}


def doctor_report() -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})

    python_ok = sys.version_info >= (3, 9)
    add(
        "python",
        "pass" if python_ok else "fail",
        f"{sys.version.split()[0]} ({sys.executable}); Python 3.9 or newer is required",
    )
    try:
        ET.fromstring("<diagram />")
        add("xml", "pass", "standard-library XML parser is available")
    except Exception as exc:  # pragma: no cover - guards broken interpreter builds
        add("xml", "fail", f"XML parser failed: {exc}")

    required = [
        SKILL_DIR / "SKILL.md",
        SKILL_DIR / "LICENSE.txt",
        SKILL_DIR / "agents/openai.yaml",
        SKILL_DIR / "references/diagram-ir.schema.json",
        SKILL_DIR / "references/bundle.schema.json",
        SKILL_DIR / "references/security-report.schema.json",
        SKILL_DIR / "references/migration-report.schema.json",
        SKILL_DIR / "references/export-report.schema.json",
        SKILL_DIR / "references/compatibility.md",
        SKILL_DIR / "references/security.md",
        SKILL_DIR / "references/desktop-export.md",
        ASSET_DIR / "shape-registry.json",
        ASSET_DIR / "example.architecture.json",
        ASSET_DIR / "example.erd.json",
        ASSET_DIR / "example.ha.json",
    ]
    missing = [str(path.relative_to(SKILL_DIR)) for path in required if not path.is_file()]
    add(
        "skill-files",
        "fail" if missing else "pass",
        f"missing: {', '.join(missing)}" if missing else f"{len(required)} required files are present",
    )
    try:
        registry = json.loads((ASSET_DIR / "shape-registry.json").read_text(encoding="utf-8"))
        valid_registry = isinstance(registry, dict) and bool(registry)
        add(
            "shape-registry",
            "pass" if valid_registry else "fail",
            "shape registry is readable" if valid_registry else "shape registry is empty or invalid",
        )
    except (OSError, json.JSONDecodeError) as exc:
        add("shape-registry", "fail", f"shape registry failed to load: {exc}")

    yaml_available = importlib.util.find_spec("yaml") is not None
    add(
        "yaml",
        "pass" if yaml_available else "optional",
        "PyYAML is available" if yaml_available else "PyYAML is not installed; JSON workflows remain available",
    )
    desktop = find_drawio()
    add(
        "drawio-desktop",
        "pass" if desktop else "optional",
        desktop or "draw.io Desktop was not found; editable .drawio and SVG preview generation remain available",
    )
    failures = [check for check in checks if check["status"] == "fail"]
    return {
        "tool": "drawio-diagram-engineer",
        "version": VERSION,
        "ready": not failures,
        "checks": checks,
        "capabilities": {
            "editable_drawio": not failures,
            "svg_preview": not failures,
            "yaml_input": yaml_available,
            "desktop_export": desktop is not None,
        },
    }


def command_doctor(args: argparse.Namespace) -> int:
    report = doctor_report()
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"drawio-diagram-engineer {report['version']}")
        for check in report["checks"]:
            print(f"[{check['status'].upper():8}] {check['name']}: {check['message']}")
        print(
            "\nReady for core workflows."
            if report["ready"]
            else "\nCore workflow is not ready. Fix the FAIL checks above."
        )
    return 0 if report["ready"] else 2


def command_init(args: argparse.Namespace) -> int:
    asset_name, default_name = STARTER_PROFILES[args.profile]
    source = ASSET_DIR / asset_name
    output = Path(args.output or default_name)
    if output.exists() and not args.force:
        raise ValueError(f"{output} already exists; choose another path or pass --force")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    build_output = Path("build") / slugify(output.stem)
    next_command = (
        f"{Path(sys.executable).name} {Path(__file__).resolve()} build {output} "
        f"-o {build_output} --strict"
    )
    print(json.dumps({
        "profile": args.profile,
        "output": str(output),
        "next": next_command,
    }, indent=2, ensure_ascii=False))
    return 0


def prepare_build_model(
    path: Path,
    build_type: str,
    title: str | None,
    max_files: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    selected = build_type
    loaded: dict[str, Any] | None = None
    if selected == "auto" and path.is_file() and path.suffix.lower() in {".json", ".yaml", ".yml"}:
        loaded = load_data(path)
        if "blueprint" in loaded:
            selected = "blueprint"
        elif "erd" in loaded:
            selected = "erd"
        elif "ha" in loaded:
            selected = "ha"
        elif "version" in loaded and (
            "diagram" in loaded or "pages" in loaded or "nodes" in loaded
        ):
            selected = "diagram"
    if selected == "auto" and path.suffix.lower() == ".sql":
        selected = "sql-erd"

    if selected == "diagram":
        data = loaded or load_data(path)
        return data, [], "diagram"
    if selected == "blueprint":
        data = loaded or load_data(path)
        issues = validate_blueprint(data)
        return blueprint_to_ir(data), issues, "blueprint"
    if selected in {"erd", "sql-erd"}:
        data = (
            sql_to_erd(path.read_text(encoding="utf-8"), title or path.stem)
            if selected == "sql-erd" or path.suffix.lower() == ".sql"
            else (loaded or load_data(path))
        )
        issues = validate_erd(data)
        return erd_to_ir(data), issues, "erd"
    if selected == "ha":
        data = loaded or load_data(path)
        issues = validate_ha(data)
        return ha_to_ir(data), issues, "ha"
    data = import_source(path, selected, title, max_files)
    return data, [], selected


def command_build(args: argparse.Namespace) -> int:
    source = Path(args.input)
    if not source.exists():
        raise ValueError(f"input does not exist: {source}")
    output = Path(args.output) if args.output else Path("build") / slugify(source.stem)
    if output.exists() and not output.is_dir():
        raise ValueError(f"output must be a directory: {output}")
    if output.exists() and any(output.iterdir()):
        marker = output / "bundle.json"
        if not args.force:
            raise ValueError(f"{output} is not empty; choose another directory or pass --force")
        if not marker.is_file():
            raise ValueError(f"refusing to replace unrecognized directory {output}; bundle.json is missing")
        try:
            marker_data = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"refusing to replace invalid bundle directory {output}") from exc
        if marker_data.get("generator") != "drawio-diagram-engineer":
            raise ValueError(f"refusing to replace directory not owned by drawio-diagram-engineer: {output}")

    diagram_ir, source_issues, model_type = prepare_build_model(
        source, args.type, args.title, args.max_files,
    )
    if args.theme_file:
        diagram_ir = apply_theme_pack(diagram_ir, load_theme_pack(Path(args.theme_file)))
    security = security_report_for_data(diagram_ir, source.name)
    ir_issues = validate_ir(diagram_ir)
    initial_issues = source_issues + ir_issues + security["findings"]
    if any(item["level"] == "error" for item in initial_issues):
        print_report(initial_issues, {"model": model_type, "input": str(source)})
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{slugify(output.name)}-", dir=str(output.parent)))
    try:
        name = slugify(args.name or source.stem)
        ir_path = staging / "diagram.json"
        drawio_path = staging / f"{name}.drawio"
        preview_dir = staging / "previews"
        preview_dir.mkdir()
        ir_path.write_text(
            json.dumps(diagram_ir, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        compile_drawio(diagram_ir).write(drawio_path, encoding="utf-8", xml_declaration=True)
        drawio_issues, summary = validate_drawio(drawio_path)
        preview_names = []
        for page_id, page in page_documents(diagram_ir):
            preview_name = f"{page_id}.svg"
            compile_svg(page).write(
                preview_dir / preview_name, encoding="utf-8", xml_declaration=True,
            )
            preview_names.append(f"previews/{preview_name}")
        all_issues = initial_issues + drawio_issues
        audit = build_audit_report(all_issues, summary, preview_names)
        (staging / "audit.json").write_text(
            json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (staging / "security.json").write_text(
            json.dumps(security, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "format": BUNDLE_FORMAT,
            "generator": "drawio-diagram-engineer",
            "tool_version": VERSION,
            "name": name,
            "model": model_type,
            "source": {"name": source.name, "included": False},
            "score": audit["score"],
            "artifacts": {
                "ir": "diagram.json",
                "drawio": f"{name}.drawio",
                "audit": "audit.json",
                "security": "security.json",
                "previews": preview_names,
            },
        }
        (staging / "bundle.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            if any(output.iterdir()):
                shutil.rmtree(output)
            else:
                output.rmdir()
        staging.replace(output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    print(json.dumps({
        "output": str(output),
        "model": model_type,
        "score": audit["score"],
        "drawio": str(output / manifest["artifacts"]["drawio"]),
        "previews": [str(output / item) for item in preview_names],
        "audit": str(output / "audit.json"),
        "security": str(output / "security.json"),
    }, indent=2, ensure_ascii=False))
    if audit["errors"]:
        return 2
    if args.strict and audit["score"] < 90:
        return 3
    return 0


def command_compile(args: argparse.Namespace) -> int:
    path = Path(args.input)
    data = load_data(path)
    if args.theme_file:
        data = apply_theme_pack(data, load_theme_pack(Path(args.theme_file)))
    issues = validate_ir(data)
    if any(item["level"] == "error" for item in issues):
        print_report(issues)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    compile_drawio(data).write(output, encoding="utf-8", xml_declaration=True)
    documents = page_documents(data)
    print_report(issues, {
        "output": str(output),
        "pages": len(documents),
        "nodes": sum(len(page.get("nodes", [])) for _, page in documents),
        "edges": sum(len(page.get("edges", [])) for _, page in documents),
    })
    return 0


def command_extract(args: argparse.Namespace) -> int:
    source = Path(args.input)
    extracted, report = extract_drawio(source)
    output = Path(args.output)
    report["output"] = str(output)
    if report["passed"]:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(extracted, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["passed"]:
        return 2
    if args.strict and not report["lossless"]:
        return 3
    return 0


def command_import(args: argparse.Namespace) -> int:
    data = import_source(Path(args.input), args.type, args.title, args.max_files)
    issues = validate_ir(data)
    if any(item["level"] == "error" for item in issues):
        print_report(issues)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print_report(issues, {
        "output": str(output), "type": args.type,
        "nodes": len(data.get("nodes", [])), "edges": len(data.get("edges", [])),
    })
    return 0


def command_diff(args: argparse.Namespace) -> int:
    baseline_path = Path(args.baseline)
    candidate_path = Path(args.candidate)
    baseline = load_data(baseline_path)
    candidate = load_data(candidate_path)
    report = architecture_diff(
        baseline, candidate, str(baseline_path), str(candidate_path),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    generated_ir: dict[str, Any] | None = None
    if args.diagram_output or args.preview_dir:
        generated_ir = drift_diagram(baseline, candidate, report)
        drift_issues = validate_ir(generated_ir)
        errors = [item for item in drift_issues if item["level"] == "error"]
        if errors:
            raise ValueError(f"cannot generate drift diagram: {errors[0]['message']}")
    if args.diagram_output and generated_ir is not None:
        diagram_output = Path(args.diagram_output)
        diagram_output.parent.mkdir(parents=True, exist_ok=True)
        compile_drawio(generated_ir).write(
            diagram_output, encoding="utf-8", xml_declaration=True,
        )
    if args.preview_dir and generated_ir is not None:
        preview_dir = Path(args.preview_dir)
        preview_dir.mkdir(parents=True, exist_ok=True)
        for page_id, page in page_documents(generated_ir):
            compile_svg(page).write(
                preview_dir / f"{page_id}.svg",
                encoding="utf-8",
                xml_declaration=True,
            )
    print(json.dumps({
        "output": str(output),
        "diagram_output": str(args.diagram_output) if args.diagram_output else None,
        "preview_dir": str(args.preview_dir) if args.preview_dir else None,
        "drift": report["drift"],
        "summary": report["summary"],
    }, indent=2, ensure_ascii=False))
    return 5 if args.fail_on_drift and report["drift"] else 0


def write_generated_model(
    diagram_ir: dict[str, Any],
    source_issues: list[dict[str, Any]],
    args: argparse.Namespace,
    model_type: str,
) -> int:
    if args.theme_file:
        diagram_ir = apply_theme_pack(diagram_ir, load_theme_pack(Path(args.theme_file)))
    ir_issues = validate_ir(diagram_ir)
    if any(item["level"] == "error" for item in ir_issues):
        print_report(source_issues + ir_issues)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    compile_drawio(diagram_ir).write(output, encoding="utf-8", xml_declaration=True)
    drawio_issues, drawio_summary = validate_drawio(output)
    if args.ir_output:
        ir_output = Path(args.ir_output)
        ir_output.parent.mkdir(parents=True, exist_ok=True)
        ir_output.write_text(
            json.dumps(diagram_ir, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.preview_dir:
        preview_dir = Path(args.preview_dir)
        preview_dir.mkdir(parents=True, exist_ok=True)
        for page_id, page in page_documents(diagram_ir):
            compile_svg(page).write(
                preview_dir / f"{page_id}.svg",
                encoding="utf-8",
                xml_declaration=True,
            )
    all_issues = source_issues + ir_issues + drawio_issues
    print_report(all_issues, {
        **drawio_summary,
        "model": model_type,
        "output": str(output),
        "ir_output": str(args.ir_output) if args.ir_output else None,
        "preview_dir": str(args.preview_dir) if args.preview_dir else None,
    })
    if any(item["level"] == "error" for item in all_issues):
        return 2
    if args.strict and score_issues(all_issues) < 90:
        return 3
    return 0


def command_erd(args: argparse.Namespace) -> int:
    path = Path(args.input)
    source = (
        sql_to_erd(path.read_text(encoding="utf-8"), args.title or path.stem)
        if path.suffix.lower() == ".sql"
        else load_data(path)
    )
    source_issues = validate_erd(source)
    if any(item["level"] == "error" for item in source_issues):
        print_report(source_issues)
        return 2
    return write_generated_model(erd_to_ir(source), source_issues, args, "erd")


def command_ha(args: argparse.Namespace) -> int:
    source = load_data(Path(args.input))
    source_issues = validate_ha(source)
    if any(item["level"] == "error" for item in source_issues):
        print_report(source_issues)
        return 2
    return write_generated_model(ha_to_ir(source), source_issues, args, "ha")


def command_blueprint(args: argparse.Namespace) -> int:
    source = load_data(Path(args.input))
    source_issues = validate_blueprint(source)
    if any(item["level"] == "error" for item in source_issues):
        print_report(source_issues)
        return 2
    views = [item.strip() for item in args.views.split(",") if item.strip()] if args.views else None
    diagram_ir = blueprint_to_ir(source, views)
    if args.theme_file:
        diagram_ir = apply_theme_pack(diagram_ir, load_theme_pack(Path(args.theme_file)))
    ir_issues = validate_ir(diagram_ir)
    if any(item["level"] == "error" for item in ir_issues):
        print_report(source_issues + ir_issues)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    compile_drawio(diagram_ir).write(output, encoding="utf-8", xml_declaration=True)
    drawio_issues, drawio_summary = validate_drawio(output)
    if args.ir_output:
        ir_output = Path(args.ir_output)
        ir_output.parent.mkdir(parents=True, exist_ok=True)
        ir_output.write_text(
            json.dumps(diagram_ir, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.preview_dir:
        preview_dir = Path(args.preview_dir)
        preview_dir.mkdir(parents=True, exist_ok=True)
        for page_id, page in page_documents(diagram_ir):
            compile_svg(page).write(
                preview_dir / f"{page_id}.svg",
                encoding="utf-8",
                xml_declaration=True,
            )
    all_issues = source_issues + ir_issues + drawio_issues
    summary = {
        **drawio_summary,
        "output": str(output),
        "ir_output": str(args.ir_output) if args.ir_output else None,
        "preview_dir": str(args.preview_dir) if args.preview_dir else None,
    }
    print_report(all_issues, summary)
    if any(item["level"] == "error" for item in all_issues):
        return 2
    if args.strict and score_issues(all_issues) < 90:
        return 3
    return 0


def command_patch(args: argparse.Namespace) -> int:
    data = load_data(Path(args.input))
    patch_data = load_data(Path(args.patch))
    operations = patch_data.get("operations")
    if not isinstance(operations, list):
        raise ValueError("patch file requires an operations array")
    result = apply_ir_operations(data, operations)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print_report(validate_ir(result), {"output": str(output), "operations": len(operations)})
    return 0


def command_preview(args: argparse.Namespace) -> int:
    data = load_data(Path(args.input))
    if args.theme_file:
        data = apply_theme_pack(data, load_theme_pack(Path(args.theme_file)))
    issues = validate_ir(data)
    if any(item["level"] == "error" for item in issues):
        print_report(issues)
        return 2
    page = select_page(data, args.page)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    compile_svg(page).write(output, encoding="utf-8", xml_declaration=True)
    print_report(issues, {"output": str(output), "page": args.page or "main"})
    return 0


def command_audit(args: argparse.Namespace) -> int:
    path = Path(args.input)
    previews: list[str] = []
    if path.suffix.lower() == ".drawio":
        issues, summary = validate_drawio(path)
    else:
        source = load_data(path)
        if "blueprint" in source:
            issues = validate_blueprint(source)
            diagram_ir = blueprint_to_ir(source) if not any(item["level"] == "error" for item in issues) else None
        elif "erd" in source:
            issues = validate_erd(source)
            diagram_ir = erd_to_ir(source) if not any(item["level"] == "error" for item in issues) else None
        elif "ha" in source:
            issues = validate_ha(source)
            diagram_ir = ha_to_ir(source) if not any(item["level"] == "error" for item in issues) else None
        else:
            diagram_ir = source
            issues = []
        if diagram_ir is not None:
            if args.theme_file:
                diagram_ir = apply_theme_pack(diagram_ir, load_theme_pack(Path(args.theme_file)))
            issues.extend(validate_ir(diagram_ir))
            documents = page_documents(diagram_ir)
            if not any(item["level"] == "error" for item in issues):
                with tempfile.TemporaryDirectory() as directory:
                    generated = Path(directory) / "audit.drawio"
                    compile_drawio(diagram_ir).write(
                        generated, encoding="utf-8", xml_declaration=True
                    )
                    generated_issues, summary = validate_drawio(generated)
                issues.extend(generated_issues)
            else:
                summary = {
                    "pages": len(documents),
                    "nodes": sum(len(page.get("nodes", [])) for _, page in documents),
                    "edges": sum(len(page.get("edges", [])) for _, page in documents),
                    "groups": sum(len(page.get("groups", [])) for _, page in documents),
                }
            if args.preview_dir and not any(item["level"] == "error" for item in issues):
                preview_dir = Path(args.preview_dir)
                preview_dir.mkdir(parents=True, exist_ok=True)
                for page_id, page in documents:
                    preview_path = preview_dir / f"{page_id}.svg"
                    compile_svg(page).write(preview_path, encoding="utf-8", xml_declaration=True)
                    previews.append(str(preview_path))
        else:
            summary = {"pages": 0, "nodes": 0, "edges": 0, "groups": 0}
    report = build_audit_report(issues, summary, previews)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["errors"]:
        return 2
    if args.strict and report["score"] < 90:
        return 3
    return 0


def command_validate(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if path.suffix.lower() == ".drawio":
        issues, summary = validate_drawio(path)
    else:
        data = load_data(path)
        if "blueprint" in data:
            issues = validate_blueprint(data)
            summary = {
                "model": "blueprint",
                "elements": len(data.get("elements", [])),
                "relations": len(data.get("relations", [])),
                "decisions": len(data.get("decisions", [])),
            }
        elif "erd" in data:
            issues = validate_erd(data)
            summary = {
                "model": "erd",
                "entities": len(data.get("entities", [])),
                "relationships": len(data.get("relationships", [])),
            }
        elif "ha" in data:
            issues = validate_ha(data)
            summary = {
                "model": "ha",
                "domains": len(data.get("domains", [])),
                "components": len(data.get("components", [])),
                "failovers": len(data.get("failovers", [])),
            }
        else:
            documents = page_documents(data)
            issues, summary = validate_ir(data), {
                "pages": len(documents),
                "nodes": sum(len(page.get("nodes", [])) for _, page in documents),
                "edges": sum(len(page.get("edges", [])) for _, page in documents),
                "groups": sum(len(page.get("groups", [])) for _, page in documents),
            }
    print_report(issues, summary)
    score = score_issues(issues)
    if any(item["level"] == "error" for item in issues):
        return 2
    if args.strict and score < 90:
        return 3
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    path = Path(args.input)
    issues, summary = validate_drawio(path)
    labels = []
    for cell in load_drawio_root(path).findall(".//mxCell[@vertex='1']"):
        if "swimlane=1" not in cell.get("style", ""):
            labels.append({"id": cell.get("id"), "label": cell.get("value", "")})
    summary["labels"] = labels
    print(json.dumps({"summary": summary, "score": score_issues(issues), "issues": issues}, indent=2, ensure_ascii=False))
    return 0


def command_render(args: argparse.Namespace) -> int:
    binary = find_drawio(args.binary)
    if not binary:
        print("draw.io Desktop CLI was not found", file=sys.stderr)
        return 4
    output = Path(args.output)
    fmt = args.format or output.suffix.lstrip(".").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in {"png", "svg", "pdf", "jpg"}:
        print(f"unsupported export format: {fmt}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=f".{fmt}", dir=output.parent
    )
    os.close(descriptor)
    temporary_output = Path(temporary_name)
    temporary_output.unlink()
    command = drawio_export_command(
        binary,
        Path(args.input),
        temporary_output,
        fmt,
        args.width,
        args.embed,
    )
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        temporary_output.unlink(missing_ok=True)
        raise
    if completed.returncode != 0:
        temporary_output.unlink(missing_ok=True)
        print(completed.stderr or completed.stdout, file=sys.stderr)
        return 2
    if not temporary_output.is_file():
        print("draw.io Desktop reported success but did not create the requested output", file=sys.stderr)
        return 2
    report = verify_export(temporary_output, fmt)
    report["source"] = str(output)
    report["binary"] = binary
    if report["passed"]:
        temporary_output.replace(output)
    else:
        temporary_output.unlink(missing_ok=True)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


def export_finding(code: str, message: str) -> dict[str, str]:
    return {"level": "error", "code": code, "message": message}


def numeric_svg_dimension(value: str | None) -> float | None:
    if not value:
        return None
    match = re.fullmatch(
        r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px|pt|pc|mm|cm|in)?\s*",
        value,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def verify_export(path: Path, expected_format: str | None = None) -> dict[str, Any]:
    normalized = (expected_format or path.suffix.lstrip(".")).lower()
    if normalized == "jpeg":
        normalized = "jpg"
    findings: list[dict[str, str]] = []
    report: dict[str, Any] = {
        "format": "drawio-export-report/v1",
        "source": str(path),
        "expected_format": normalized,
        "detected_format": None,
        "size_bytes": 0,
        "passed": False,
        "findings": findings,
    }
    if normalized not in {"png", "svg", "pdf", "jpg"}:
        findings.append(export_finding(
            "export.format", f"unsupported expected export format: {normalized or '(empty)'}"
        ))
        return report
    if not path.is_file():
        findings.append(export_finding("export.missing", "export file does not exist"))
        return report
    size = path.stat().st_size
    report["size_bytes"] = size
    if size == 0:
        findings.append(export_finding("export.empty", "export file is empty"))
        return report

    with path.open("rb") as stream:
        header = stream.read(512)
        if size > 2048:
            stream.seek(-2048, os.SEEK_END)
        else:
            stream.seek(0)
        trailer = stream.read()
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "png"
    elif header.startswith(b"%PDF-"):
        detected = "pdf"
    elif header.startswith(b"\xff\xd8\xff"):
        detected = "jpg"
    elif (
        b"<svg" in header.lstrip(b"\xef\xbb\xbf \t\r\n")
        or header.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<?xml")
    ):
        detected = "svg"
    else:
        detected = None
    report["detected_format"] = detected
    if detected != normalized:
        findings.append(export_finding(
            "export.signature",
            f"file signature is {detected or 'unknown'}, expected {normalized}",
        ))
        return report

    if detected == "png":
        if len(header) < 24 or header[12:16] != b"IHDR":
            findings.append(export_finding("export.png.ihdr", "PNG is missing a complete IHDR chunk"))
        else:
            width = int.from_bytes(header[16:20], "big")
            height = int.from_bytes(header[20:24], "big")
            report["dimensions"] = {"width": width, "height": height}
            if width <= 0 or height <= 0:
                findings.append(export_finding(
                    "export.dimensions", "PNG width and height must be positive"
                ))
        if not trailer.endswith(b"IEND\xaeB`\x82"):
            findings.append(export_finding(
                "export.png.iend", "PNG is missing its terminal IEND chunk"
            ))
    elif detected == "jpg":
        if not trailer.endswith(b"\xff\xd9"):
            findings.append(export_finding(
                "export.jpeg.eoi", "JPEG is missing its end-of-image marker"
            ))
    elif detected == "pdf":
        if b"%%EOF" not in trailer:
            findings.append(export_finding("export.pdf.eof", "PDF is missing its EOF marker"))
    else:
        if size > MAX_XML_INPUT_BYTES:
            findings.append(export_finding(
                "export.svg.size",
                f"SVG exceeds {MAX_XML_INPUT_BYTES // (1024 * 1024)} MiB safety limit",
            ))
        else:
            raw_svg = path.read_bytes()
            if (
                re.search(br"<!ENTITY", raw_svg, re.IGNORECASE)
                or re.search(br"<!DOCTYPE[^>]*\[", raw_svg, re.IGNORECASE | re.DOTALL)
            ):
                findings.append(export_finding(
                    "export.svg.dtd",
                    "SVG contains a prohibited entity or internal DTD declaration",
                ))
            else:
                try:
                    root = ET.fromstring(raw_svg)
                except ET.ParseError as exc:
                    findings.append(export_finding(
                        "export.svg.xml", f"SVG XML is malformed: {exc}"
                    ))
                else:
                    if root.tag.rsplit("}", 1)[-1] != "svg":
                        findings.append(export_finding(
                            "export.svg.root", "SVG document root must be <svg>"
                        ))
                    width = numeric_svg_dimension(root.get("width"))
                    height = numeric_svg_dimension(root.get("height"))
                    view_box = root.get("viewBox", "").replace(",", " ").split()
                    view_box_values: list[float] = []
                    try:
                        view_box_values = [float(value) for value in view_box]
                    except ValueError:
                        pass
                    if (width is None or height is None) and len(view_box_values) == 4:
                        width, height = view_box_values[2], view_box_values[3]
                    if width is not None and height is not None:
                        report["dimensions"] = {"width": width, "height": height}
                    if width is None or height is None or width <= 0 or height <= 0:
                        findings.append(export_finding(
                            "export.dimensions",
                            "SVG requires positive width/height or a positive viewBox",
                        ))
                    drawable = [
                        element for element in root.iter()
                        if element is not root
                        and element.tag.rsplit("}", 1)[-1]
                        not in {"defs", "style", "title", "desc", "metadata"}
                    ]
                    if not drawable:
                        findings.append(export_finding(
                            "export.svg.content", "SVG contains no drawable content"
                        ))
    report["passed"] = not findings
    return report


def command_verify_export(args: argparse.Namespace) -> int:
    report = verify_export(Path(args.input), args.format)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


def drawio_export_command(
    binary: str,
    input_path: Path,
    output_path: Path,
    output_format: str,
    width: int = 2000,
    embed: bool = False,
) -> list[str]:
    command = [
        binary, "--disable-update", "-x", "-f", output_format,
        "-o", str(output_path),
    ]
    if output_format == "png":
        command += ["--width", str(width)]
    if embed and output_format in {"png", "svg", "pdf"}:
        command.append("-e")
    command.append(str(input_path))
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="check core and optional capabilities")
    doctor_parser.add_argument("--format", choices=["human", "json"], default="human")
    doctor_parser.set_defaults(func=command_doctor)

    init_parser = subparsers.add_parser("init", help="copy a starter model into the current project")
    init_parser.add_argument("profile", choices=sorted(STARTER_PROFILES))
    init_parser.add_argument("-o", "--output")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=command_init)

    build_one_parser = subparsers.add_parser(
        "build", help="create an editable diagram, previews, IR, and audit in one bundle"
    )
    build_one_parser.add_argument("input")
    build_one_parser.add_argument("-o", "--output")
    build_one_parser.add_argument(
        "--type",
        choices=[
            "auto", "diagram", "blueprint", "erd", "sql-erd", "ha",
            "python", "typescript", "openapi", "sql", "compose",
            "terraform", "kubernetes", "github-actions", "gitlab-ci",
        ],
        default="auto",
    )
    build_one_parser.add_argument("--name")
    build_one_parser.add_argument("--title")
    build_one_parser.add_argument("--theme-file")
    build_one_parser.add_argument("--max-files", type=int, default=500)
    build_one_parser.add_argument("--strict", action="store_true")
    build_one_parser.add_argument("--force", action="store_true")
    build_one_parser.set_defaults(func=command_build)

    compile_parser = subparsers.add_parser("compile", help="compile Diagram IR to .drawio")
    compile_parser.add_argument("input")
    compile_parser.add_argument("-o", "--output", required=True)
    compile_parser.add_argument("--theme-file")
    compile_parser.set_defaults(func=command_compile)

    extract_parser = subparsers.add_parser(
        "extract", help="recover Diagram IR from an editable .drawio file"
    )
    extract_parser.add_argument("input")
    extract_parser.add_argument("-o", "--output", required=True)
    extract_parser.add_argument("--report", help="write the extraction report")
    extract_parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when any page or cell required semantic inference",
    )
    extract_parser.set_defaults(func=command_extract)

    import_parser = subparsers.add_parser(
        "import",
        help="convert source, infrastructure, and pipeline definitions to Diagram IR",
    )
    import_parser.add_argument("input")
    import_parser.add_argument("-o", "--output", required=True)
    import_parser.add_argument(
        "--type",
        choices=[
            "auto", "python", "typescript", "openapi", "sql", "compose",
            "terraform", "kubernetes", "github-actions", "gitlab-ci",
        ],
        default="auto",
    )
    import_parser.add_argument("--title")
    import_parser.add_argument("--max-files", type=int, default=500)
    import_parser.set_defaults(func=command_import)

    migrate_parser = subparsers.add_parser(
        "migrate", help="upgrade legacy or non-canonical Diagram IR to the v1 contract"
    )
    migrate_parser.add_argument("input")
    migrate_parser.add_argument("-o", "--output")
    migrate_parser.add_argument("--report")
    migrate_parser.add_argument("--check", action="store_true")
    migrate_parser.set_defaults(func=command_migrate)

    diff_parser = subparsers.add_parser(
        "diff", help="compare Diagram IR semantically and visualize architecture drift"
    )
    diff_parser.add_argument("baseline")
    diff_parser.add_argument("candidate")
    diff_parser.add_argument("-o", "--output", required=True)
    diff_parser.add_argument("--diagram-output")
    diff_parser.add_argument("--preview-dir")
    diff_parser.add_argument("--fail-on-drift", action="store_true")
    diff_parser.set_defaults(func=command_diff)

    erd_parser = subparsers.add_parser(
        "erd", help="generate a validated Crow's Foot ERD from JSON/YAML or SQL DDL"
    )
    erd_parser.add_argument("input")
    erd_parser.add_argument("-o", "--output", required=True)
    erd_parser.add_argument("--title")
    erd_parser.add_argument("--ir-output")
    erd_parser.add_argument("--preview-dir")
    erd_parser.add_argument("--theme-file")
    erd_parser.add_argument("--strict", action="store_true")
    erd_parser.set_defaults(func=command_erd)

    ha_parser = subparsers.add_parser(
        "ha", help="generate HA topology and failover views"
    )
    ha_parser.add_argument("input")
    ha_parser.add_argument("-o", "--output", required=True)
    ha_parser.add_argument("--ir-output")
    ha_parser.add_argument("--preview-dir")
    ha_parser.add_argument("--theme-file")
    ha_parser.add_argument("--strict", action="store_true")
    ha_parser.set_defaults(func=command_ha)

    blueprint_parser = subparsers.add_parser(
        "blueprint", help="generate a multi-view architecture blueprint"
    )
    blueprint_parser.add_argument("input")
    blueprint_parser.add_argument("-o", "--output", required=True)
    blueprint_parser.add_argument("--ir-output")
    blueprint_parser.add_argument("--preview-dir")
    blueprint_parser.add_argument(
        "--views",
        help="comma-separated context,logical,data,deployment,security,decisions views",
    )
    blueprint_parser.add_argument("--strict", action="store_true")
    blueprint_parser.add_argument("--theme-file")
    blueprint_parser.set_defaults(func=command_blueprint)

    patch_parser = subparsers.add_parser("patch", help="apply atomic semantic operations to Diagram IR")
    patch_parser.add_argument("input")
    patch_parser.add_argument("patch")
    patch_parser.add_argument("-o", "--output", required=True)
    patch_parser.set_defaults(func=command_patch)

    preview_parser = subparsers.add_parser("preview", help="create a dependency-free SVG review preview")
    preview_parser.add_argument("input")
    preview_parser.add_argument("-o", "--output", required=True)
    preview_parser.add_argument("--page")
    preview_parser.add_argument("--theme-file")
    preview_parser.set_defaults(func=command_preview)

    audit_parser = subparsers.add_parser(
        "audit", help="produce a quality report, repair suggestions, and review previews"
    )
    audit_parser.add_argument("input")
    audit_parser.add_argument("-o", "--output")
    audit_parser.add_argument("--preview-dir")
    audit_parser.add_argument("--theme-file")
    audit_parser.add_argument("--strict", action="store_true")
    audit_parser.set_defaults(func=command_audit)

    security_parser = subparsers.add_parser(
        "security", help="scan a model, draw.io file, or bundle for unsafe embedded content"
    )
    security_parser.add_argument("input")
    security_parser.add_argument("-o", "--output")
    security_parser.add_argument("--strict", action="store_true")
    security_parser.set_defaults(func=command_security)

    validate_parser = subparsers.add_parser("validate", help="validate Diagram IR or .drawio")
    validate_parser.add_argument("input")
    validate_parser.add_argument("--strict", action="store_true")
    validate_parser.set_defaults(func=command_validate)

    inspect_parser = subparsers.add_parser("inspect", help="summarize a .drawio file")
    inspect_parser.add_argument("input")
    inspect_parser.set_defaults(func=command_inspect)

    render_parser = subparsers.add_parser("render", help="export through draw.io Desktop")
    render_parser.add_argument("input")
    render_parser.add_argument("-o", "--output", required=True)
    render_parser.add_argument("-f", "--format")
    render_parser.add_argument("--width", type=int, default=2000)
    render_parser.add_argument("--embed", action="store_true")
    render_parser.add_argument("--report", help="write the export verification report")
    render_parser.add_argument(
        "--binary",
        help="draw.io Desktop executable; overrides DRAWIO_DESKTOP_BINARY and auto-discovery",
    )
    render_parser.set_defaults(func=command_render)

    verify_export_parser = subparsers.add_parser(
        "verify-export", help="validate a rendered PNG, SVG, PDF, or JPEG artifact"
    )
    verify_export_parser.add_argument("input")
    verify_export_parser.add_argument("-f", "--format", choices=["png", "svg", "pdf", "jpg", "jpeg"])
    verify_export_parser.add_argument("-o", "--output", help="write the verification report")
    verify_export_parser.set_defaults(func=command_verify_export)
    return parser


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
