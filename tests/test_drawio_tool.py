import base64
import importlib.util
import json
import tempfile
import unittest
import urllib.parse
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "skills/drawio-diagram-engineer/scripts/drawio_tool.py"
SPEC = importlib.util.spec_from_file_location("drawio_tool", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(TOOL)


def sample_ir():
    return {
        "version": "1",
        "diagram": {"title": "Test", "direction": "LR", "theme": "light"},
        "groups": [{"id": "core", "label": "Core"}],
        "nodes": [
            {"id": "client", "label": "Client", "kind": "client"},
            {"id": "api", "label": "API", "kind": "service", "group": "core"},
            {"id": "db", "label": "DB", "kind": "database", "group": "core"},
        ],
        "edges": [
            {"id": "client-api", "from": "client", "to": "api", "label": "HTTPS"},
            {"id": "api-db", "from": "api", "to": "db", "label": "SQL", "kind": "data"},
        ],
    }


class DrawioToolTests(unittest.TestCase):
    def test_compile_is_deterministic_and_valid(self):
        first = TOOL.compile_drawio(sample_ir())
        second = TOOL.compile_drawio(sample_ir())
        with tempfile.TemporaryDirectory() as directory:
            path_a = Path(directory) / "a.drawio"
            path_b = Path(directory) / "b.drawio"
            first.write(path_a, encoding="utf-8", xml_declaration=True)
            second.write(path_b, encoding="utf-8", xml_declaration=True)
            self.assertEqual(path_a.read_bytes(), path_b.read_bytes())
            issues, summary = TOOL.validate_drawio(path_a)
            self.assertEqual([], issues)
            self.assertEqual(3, summary["nodes"])
            self.assertEqual(2, summary["edges"])

    def test_ir_rejects_dangling_edge(self):
        data = sample_ir()
        data["edges"].append({"id": "bad", "from": "api", "to": "missing"})
        issues = TOOL.validate_ir(data)
        self.assertIn("edge.target", {item["code"] for item in issues})

    def test_explicit_position_is_preserved(self):
        data = sample_ir()
        data["nodes"][0]["position"] = {"x": 321, "y": 654}
        layout = TOOL.calculate_layout(data)
        self.assertEqual((321, 654), layout["client"][:2])

    def test_compressed_drawio_is_inspected(self):
        tree = TOOL.compile_drawio(sample_ir())
        model = tree.getroot().find(".//mxGraphModel")
        raw = TOOL.ET.tostring(model, encoding="unicode")
        compressor = zlib.compressobj(wbits=-15)
        compressed = compressor.compress(urllib.parse.quote(raw).encode("utf-8")) + compressor.flush()
        payload = base64.b64encode(compressed).decode("ascii")
        wrapper = f'<mxfile><diagram id="p1" name="Page-1">{payload}</diagram></mxfile>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compressed.drawio"
            path.write_text(wrapper, encoding="utf-8")
            issues, summary = TOOL.validate_drawio(path)
            self.assertEqual([], issues)
            self.assertEqual(3, summary["nodes"])

    def test_invalid_theme_is_error(self):
        data = sample_ir()
        data["diagram"]["theme"] = "neon"
        issues = TOOL.validate_ir(data)
        self.assertIn("ir.theme", {item["code"] for item in issues})

    def test_invalid_id_and_geometry_are_errors(self):
        data = sample_ir()
        data["nodes"][0]["id"] = "Bad ID"
        data["nodes"][1]["position"] = {"x": "left", "y": 10}
        data["diagram"]["gap"] = 10
        codes = {item["code"] for item in TOOL.validate_ir(data)}
        self.assertTrue({"id.format", "node.position", "ir.gap"} <= codes)

    def test_unknown_field_is_forward_compatible_warning(self):
        data = sample_ir()
        data["future"] = {"enabled": True}
        issues = TOOL.validate_ir(data)
        warning = next(item for item in issues if item["code"] == "ir.unknown-field")
        self.assertEqual("warning", warning["level"])

    def test_group_aware_layout_avoids_group_overlap(self):
        data = sample_ir()
        data["groups"].append({"id": "data", "label": "Data"})
        data["nodes"][2]["group"] = "data"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grouped.drawio"
            TOOL.compile_drawio(data).write(path, encoding="utf-8", xml_declaration=True)
            issues, _ = TOOL.validate_drawio(path)
            self.assertNotIn("layout.group-overlap", {item["code"] for item in issues})

    def test_multi_page_compilation_allows_page_local_ids_and_links(self):
        data = {
            "version": "1",
            "diagram": {"theme": "light", "direction": "LR"},
            "pages": [
                {
                    "id": "context",
                    "title": "Context",
                    "nodes": [
                        {"id": "system", "label": "System", "kind": "service", "link": "containers"},
                        {"id": "user", "label": "User", "kind": "client"},
                    ],
                    "edges": [{"id": "user-system", "from": "user", "to": "system"}],
                },
                {
                    "id": "containers",
                    "title": "Containers",
                    "nodes": [
                        {"id": "system", "label": "API", "kind": "service"},
                        {"id": "db", "label": "DB", "kind": "database"},
                    ],
                    "edges": [{"id": "system-db", "from": "system", "to": "db"}],
                },
            ],
        }
        self.assertEqual([], TOOL.validate_ir(data))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multi.drawio"
            tree = TOOL.compile_drawio(data)
            tree.write(path, encoding="utf-8", xml_declaration=True)
            issues, summary = TOOL.validate_drawio(path)
            self.assertEqual([], issues)
            self.assertEqual(2, summary["pages"])
            linked = tree.getroot().find(".//diagram[@id='page-context']//mxCell[@id='node-system']")
            self.assertEqual("data:page/id,page-containers", linked.get("link"))

    def test_patch_operations_are_atomic_and_preserve_positions(self):
        data = sample_ir()
        result = TOOL.apply_ir_operations(data, [
            {"op": "move-node", "id": "api", "position": {"x": 450, "y": 210}},
            {"op": "update-edge", "id": "client-api", "set": {"label": "mTLS"}},
            {
                "op": "add-node",
                "node": {"id": "worker", "label": "Worker", "kind": "service", "group": "core"},
            },
            {
                "op": "add-edge",
                "edge": {"id": "api-worker", "from": "api", "to": "worker", "kind": "async"},
            },
        ])
        api = next(node for node in result["nodes"] if node["id"] == "api")
        edge = next(edge for edge in result["edges"] if edge["id"] == "client-api")
        self.assertEqual({"x": 450, "y": 210}, api["position"])
        self.assertEqual("mTLS", edge["label"])
        self.assertNotIn("worker", {node["id"] for node in data["nodes"]})

    def test_patch_refuses_unsafe_node_delete(self):
        with self.assertRaisesRegex(ValueError, "cascade=true"):
            TOOL.apply_ir_operations(sample_ir(), [{"op": "remove-node", "id": "api"}])

    def test_openapi_import_builds_operations_and_schema_edges(self):
        source = {
            "openapi": "3.1.0",
            "info": {"title": "Pet API"},
            "paths": {
                "/pets": {
                    "get": {
                        "operationId": "listPets",
                        "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}}},
                    }
                }
            },
            "components": {"schemas": {"Pet": {"properties": {"id": {"type": "string"}}}}},
        }
        data = TOOL.import_openapi(source)
        self.assertEqual([], [item for item in TOOL.validate_ir(data) if item["level"] == "error"])
        self.assertIn("op-listpets", {node["id"] for node in data["nodes"]})
        self.assertTrue(any(edge["to"] == "schema-pet" for edge in data["edges"]))

    def test_sql_import_builds_foreign_key_relation(self):
        sql = """
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);
        CREATE TABLE orders (
          id INTEGER PRIMARY KEY,
          user_id INTEGER REFERENCES users(id)
        );
        """
        data = TOOL.import_sql(sql)
        self.assertEqual(2, len(data["nodes"]))
        self.assertEqual("table-users", data["edges"][0]["to"])
        self.assertEqual([], [item for item in TOOL.validate_ir(data) if item["level"] == "error"])

    def test_compose_import_builds_dependencies_and_volumes(self):
        source = {
            "services": {
                "api": {"image": "example/api", "depends_on": ["db"], "volumes": ["cache:/cache"]},
                "db": {"image": "postgres:17"},
            },
            "volumes": {"cache": {}},
        }
        data = TOOL.import_compose(source)
        self.assertIn("volume-cache", {node["id"] for node in data["nodes"]})
        self.assertTrue(any(edge["kind"] == "dependency" for edge in data["edges"]))
        self.assertEqual([], [item for item in TOOL.validate_ir(data) if item["level"] == "error"])

    def test_python_tree_import_builds_internal_import_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "shop"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "api.py").write_text("from shop import orders\n", encoding="utf-8")
            (package / "orders.py").write_text("import json\n", encoding="utf-8")
            data = TOOL.import_python_tree(root)
            labels = {node["label"] for node in data["nodes"]}
            self.assertTrue({"shop", "shop.api", "shop.orders"} <= labels)
            self.assertEqual(1, len(data["edges"]))
            id_to_label = {node["id"]: node["label"] for node in data["nodes"]}
            self.assertEqual("shop.orders", id_to_label[data["edges"][0]["to"]])
            self.assertEqual([], [item for item in TOOL.validate_ir(data) if item["level"] == "error"])

    def test_typescript_tree_import_resolves_relative_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src"
            source.mkdir()
            (source / "api.ts").write_text("import {load} from './orders';\n", encoding="utf-8")
            (source / "orders.ts").write_text("export const load = () => 1;\n", encoding="utf-8")
            data = TOOL.import_typescript_tree(root)
            self.assertEqual(2, len(data["nodes"]))
            self.assertEqual(1, len(data["edges"]))
            self.assertEqual([], [item for item in TOOL.validate_ir(data) if item["level"] == "error"])

    def test_dependency_free_svg_preview_is_valid_xml(self):
        tree = TOOL.compile_svg(sample_ir())
        root = tree.getroot()
        self.assertEqual("svg", root.tag)
        self.assertGreaterEqual(len(root.findall("rect")), 4)

    def test_blueprint_projects_six_architecture_views(self):
        source = json.loads(
            (ROOT / "skills/drawio-diagram-engineer/assets/example.blueprint.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual([], TOOL.validate_blueprint(source))
        diagram_ir = TOOL.blueprint_to_ir(source)
        pages = {page["id"]: page for page in diagram_ir["pages"]}
        self.assertEqual(
            {"context", "logical", "data", "deployment", "security", "decisions"},
            set(pages),
        )
        context_edges = {(edge["from"], edge["to"]) for edge in pages["context"]["edges"]}
        self.assertIn(("customer", "commerce"), context_edges)
        self.assertIn(("commerce", "payment"), context_edges)
        self.assertNotIn("commerce", {node["id"] for node in pages["logical"]["nodes"]})
        self.assertEqual({"direction": "TB"}, pages["deployment"]["diagram"])
        decision_edges = {
            (edge["from"], edge["to"]) for edge in pages["decisions"]["edges"]
        }
        self.assertIn(("decision-event-driven-orders", "orders"), decision_edges)
        self.assertEqual({"direction": "TB"}, pages["decisions"]["diagram"])
        self.assertEqual([], [item for item in TOOL.validate_ir(diagram_ir) if item["level"] == "error"])
        self.assertEqual(diagram_ir, TOOL.blueprint_to_ir(source))

        context_only = TOOL.blueprint_to_ir(source, ["context"])
        self.assertEqual(["context"], [page["id"] for page in context_only["pages"]])
        context_system = next(
            node for node in context_only["pages"][0]["nodes"] if node["id"] == "commerce"
        )
        self.assertNotIn("link", context_system)

    def test_blueprint_rejects_parent_cycle(self):
        source = {
            "version": "1",
            "blueprint": {"title": "Broken"},
            "elements": [
                {"id": "a", "label": "A", "scope": "system", "parent": "b"},
                {"id": "b", "label": "B", "scope": "component", "parent": "a"},
            ],
            "relations": [],
        }
        codes = {item["code"] for item in TOOL.validate_blueprint(source)}
        self.assertIn("blueprint.parent-cycle", codes)

    def test_theme_pack_is_applied_and_contrast_is_checked(self):
        theme_path = (
            ROOT
            / "skills/drawio-diagram-engineer/assets/themes/corporate.json"
        )
        tokens = TOOL.load_theme_pack(theme_path)
        themed = TOOL.apply_theme_pack(sample_ir(), tokens)
        self.assertEqual(tokens, themed["diagram"]["theme_tokens"])
        self.assertEqual([], [
            item for item in TOOL.validate_ir(themed)
            if item["level"] == "error"
        ])

        low_contrast = json.loads(json.dumps(themed))
        low_contrast["diagram"]["theme_tokens"]["font"] = "#ffffff"
        codes = {item["code"] for item in TOOL.validate_ir(low_contrast)}
        self.assertIn("theme.contrast", codes)

    def test_shape_registry_has_verified_provenance_and_kinds(self):
        registry = TOOL.load_shape_registry()
        self.assertEqual("Apache-2.0", registry["provenance"]["license"])
        self.assertTrue(
            registry["provenance"]["source"].startswith("https://github.com/jgraph/")
        )
        self.assertEqual(TOOL.ALLOWED_KINDS, set(registry["shapes"]))
        self.assertTrue(
            {
                item["shape"] for item in registry["shapes"].values()
            } <= TOOL.VERIFIED_SHAPES
        )

    def test_audit_report_groups_repairs(self):
        issues = [
            TOOL.issue("warning", "node.contrast", "low contrast", "node-api"),
            TOOL.issue("warning", "node.contrast", "low contrast", "node-db"),
            TOOL.issue("warning", "label.density", "too dense", "node-api"),
        ]
        report = TOOL.build_audit_report(
            issues, {"pages": 1, "nodes": 2, "edges": 1, "groups": 0}
        )
        repairs = {item["code"]: item for item in report["repairs"]}
        self.assertEqual(2, len(repairs["node.contrast"]["targets"]))
        self.assertIn("4.5:1", repairs["node.contrast"]["suggestion"])


if __name__ == "__main__":
    unittest.main()
