import base64
import importlib.util
import json
import tempfile
import unittest
import urllib.parse
import zlib
from pathlib import Path
from unittest import mock


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

    def test_legacy_ir_migration_is_deterministic_and_preserves_extensions(self):
        legacy = {
            "title": "Legacy",
            "direction": "LR",
            "components": [
                {"id": "user", "label": "User", "type": "user"},
                {"id": "api", "label": "API", "type": "api"},
            ],
            "connections": [
                {"source": "user", "target": "api", "type": "sync"},
            ],
            "x-owner": "platform",
        }
        first, first_report = TOOL.migrate_diagram_ir(legacy)
        second, second_report = TOOL.migrate_diagram_ir(legacy)
        self.assertEqual(first, second)
        self.assertEqual(first_report, second_report)
        self.assertEqual("1", first["version"])
        self.assertEqual("platform", first["x-owner"])
        self.assertEqual("client", first["nodes"][0]["kind"])
        self.assertEqual("user-to-api", first["edges"][0]["id"])
        self.assertTrue(first_report["changes_required"])
        self.assertNotIn("error", {item["level"] for item in first_report["issues"]})

    def test_legacy_ir_migration_rejects_ambiguous_fields(self):
        legacy = {
            "components": [],
            "nodes": [],
            "connections": [],
        }
        with self.assertRaisesRegex(ValueError, "both components and nodes"):
            TOOL.migrate_diagram_ir(legacy)

    def test_security_scan_rejects_credentials_without_echoing_them(self):
        credential = "not-for-output-123456"
        report = TOOL.security_report_for_data(
            {
                "version": "1",
                "diagram": {"title": "Unsafe"},
                "nodes": [
                    {"id": "api", "label": "API", "description": f"token={credential}"}
                ],
                "edges": [],
            },
            "unsafe.json",
        )
        self.assertFalse(report["passed"])
        self.assertIn("security.inline-secret", {item["code"] for item in report["findings"]})
        self.assertNotIn(credential, json.dumps(report))

    def test_security_scan_allows_placeholders_and_lists_external_links(self):
        report = TOOL.security_report_for_data(
            {
                "token": "${TOKEN}",
                "node": {"link": "https://example.com/architecture"},
            },
            "safe.json",
        )
        self.assertTrue(report["passed"])
        self.assertEqual(1, len(report["external_links"]))

    def test_drawio_loader_rejects_dtd(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.drawio"
            path.write_text(
                '<!DOCTYPE mxfile [<!ENTITY payload "unsafe">]>'
                '<mxfile><diagram><mxGraphModel>&payload;</mxGraphModel></diagram></mxfile>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "prohibited DTD"):
                TOOL.load_drawio_root(path)

    def test_structured_input_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_text('{"value": "' + ("x" * 100) + '"}', encoding="utf-8")
            original_limit = TOOL.MAX_STRUCTURED_INPUT_BYTES
            TOOL.MAX_STRUCTURED_INPUT_BYTES = 32
            try:
                with self.assertRaisesRegex(ValueError, "structured input exceeds"):
                    TOOL.load_data(path)
            finally:
                TOOL.MAX_STRUCTURED_INPUT_BYTES = original_limit

    def test_drawio_loader_bounds_compressed_pages(self):
        inner_xml = "<mxGraphModel><root>" + ("x" * 1000) + "</root></mxGraphModel>"
        encoded_xml = urllib.parse.quote(inner_xml).encode("utf-8")
        compressor = zlib.compressobj(wbits=-15)
        payload = base64.b64encode(compressor.compress(encoded_xml) + compressor.flush()).decode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.drawio"
            path.write_text(
                f"<mxfile><diagram name=\"Main\">{payload}</diagram></mxfile>",
                encoding="utf-8",
            )
            original_limit = TOOL.MAX_DECOMPRESSED_PAGE_BYTES
            TOOL.MAX_DECOMPRESSED_PAGE_BYTES = 64
            try:
                with self.assertRaisesRegex(ValueError, "safety limit"):
                    TOOL.load_drawio_root(path)
            finally:
                TOOL.MAX_DECOMPRESSED_PAGE_BYTES = original_limit

    def test_drawio_desktop_candidates_cover_supported_platforms(self):
        mac = TOOL.drawio_candidates(platform_name="darwin", os_name="posix")
        windows = TOOL.drawio_candidates(
            platform_name="win32",
            os_name="nt",
            environ={"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"},
        )
        linux = TOOL.drawio_candidates(platform_name="linux", os_name="posix")
        self.assertIn("/Applications/draw.io.app/Contents/MacOS/draw.io", mac)
        self.assertIn(r"C:\Program Files\draw.io\draw.io.exe", windows)
        self.assertTrue(any("LOCALAPPDATA" not in item and "Programs" in item for item in windows))
        self.assertIn("/snap/bin/drawio", linux)

    def test_drawio_export_command_is_shell_free_and_format_aware(self):
        command = TOOL.drawio_export_command(
            "/opt/drawio",
            Path("input.drawio"),
            Path("output.png"),
            "png",
            width=2400,
            embed=True,
        )
        self.assertEqual("/opt/drawio", command[0])
        self.assertIn("--width", command)
        self.assertIn("2400", command)
        self.assertIn("-e", command)
        self.assertEqual("input.drawio", command[-1])
        self.assertIn("--disable-update", command)

    def test_export_verifier_accepts_svg_png_pdf_and_jpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            exports = {
                "svg": (
                    b'<svg xmlns="http://www.w3.org/2000/svg" '
                    b'width="120px" height="80px"><rect width="1" height="1"/></svg>'
                ),
                "png": (
                    b"\x89PNG\r\n\x1a\n"
                    b"\x00\x00\x00\rIHDR"
                    b"\x00\x00\x00x\x00\x00\x00P"
                    b"\x08\x06\x00\x00\x00"
                    b"\x00\x00\x00\x00IEND\xaeB`\x82"
                ),
                "pdf": b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n",
                "jpg": b"\xff\xd8\xff\xe0example\xff\xd9",
            }
            for export_format, content in exports.items():
                path = temp / f"diagram.{export_format}"
                path.write_bytes(content)
                report = TOOL.verify_export(path, export_format)
                self.assertTrue(report["passed"], report)
                self.assertEqual(export_format, report["detected_format"])
            self.assertEqual(
                {"width": 120, "height": 80},
                TOOL.verify_export(temp / "diagram.png")["dimensions"],
            )

    def test_export_verifier_rejects_truncated_and_mismatched_files(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            truncated = temp / "truncated.png"
            truncated.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x10\x00\x00\x00\x10"
            )
            truncated_report = TOOL.verify_export(truncated)
            self.assertFalse(truncated_report["passed"])
            self.assertIn(
                "export.png.iend",
                {item["code"] for item in truncated_report["findings"]},
            )
            disguised = temp / "disguised.pdf"
            disguised.write_text(
                '<svg width="10" height="10"><rect width="1" height="1"/></svg>',
                encoding="utf-8",
            )
            mismatch_report = TOOL.verify_export(disguised)
            self.assertFalse(mismatch_report["passed"])
            self.assertEqual("svg", mismatch_report["detected_format"])

    def test_render_writes_a_verified_report(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            binary = temp / "drawio"
            binary.write_text("placeholder", encoding="utf-8")
            binary.chmod(0o755)
            source = temp / "source.drawio"
            source.write_text("<mxfile />", encoding="utf-8")
            output = temp / "export.svg"
            report_path = temp / "report.json"
            args = mock.Mock(
                binary=str(binary),
                output=str(output),
                input=str(source),
                format="svg",
                width=2000,
                embed=False,
                report=str(report_path),
            )

            def fake_run(command, **_kwargs):
                generated = Path(command[command.index("-o") + 1])
                generated.write_text(
                    '<svg width="100" height="50"><rect width="10" height="10"/></svg>',
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(TOOL.subprocess, "run", side_effect=fake_run):
                self.assertEqual(0, TOOL.command_render(args))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertEqual(str(binary), report["binary"])

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

    def test_explicit_edge_ports_are_compiled_to_drawio_anchors(self):
        data = sample_ir()
        data["edges"][0]["style"] = {
            "source_port": "north",
            "source_offset": 0.25,
            "target_port": "south",
            "target_offset": 0.75,
        }
        tree = TOOL.compile_drawio(data)
        edge = tree.getroot().find(".//mxCell[@id='edge-client-api']")
        self.assertIsNotNone(edge)
        style = TOOL.parse_style_values(edge.get("style", ""))
        self.assertEqual(("0.25", "0", "0.75", "1"), (
            style["exitX"], style["exitY"], style["entryX"], style["entryY"],
        ))
        self.assertTrue(edge.findall("./mxGeometry/Array[@as='points']/mxPoint"))

    def test_automatic_fanout_uses_distinct_source_ports(self):
        data = {
            "version": "1",
            "diagram": {"title": "Fanout", "direction": "LR", "theme": "colorblind"},
            "groups": [],
            "nodes": [
                {"id": "gateway", "label": "Gateway"},
                {"id": "orders", "label": "Orders"},
                {"id": "payments", "label": "Payments"},
                {"id": "profile", "label": "Profile"},
            ],
            "edges": [
                {"id": "gateway-orders", "from": "gateway", "to": "orders"},
                {"id": "gateway-payments", "from": "gateway", "to": "payments"},
                {"id": "gateway-profile", "from": "gateway", "to": "profile"},
            ],
        }
        tree = TOOL.compile_drawio(data)
        exit_offsets = {
            TOOL.parse_style_values(edge.get("style", ""))["exitY"]
            for edge in tree.getroot().findall(".//mxCell[@edge='1']")
        }
        self.assertEqual(3, len(exit_offsets))
        self.assertEqual({"0.18", "0.5", "0.82"}, exit_offsets)

    def test_orthogonal_router_avoids_blocking_node(self):
        data = {
            "version": "1",
            "diagram": {"title": "Obstacle", "direction": "LR", "theme": "colorblind"},
            "groups": [],
            "nodes": [
                {
                    "id": "source", "label": "Source",
                    "position": {"x": 100, "y": 220},
                },
                {
                    "id": "blocker", "label": "Blocker",
                    "position": {"x": 430, "y": 220},
                },
                {
                    "id": "target", "label": "Target",
                    "position": {"x": 760, "y": 220},
                },
            ],
            "edges": [{"id": "source-target", "from": "source", "to": "target"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            drawio = Path(directory) / "routed.drawio"
            TOOL.compile_drawio(data).write(
                drawio, encoding="utf-8", xml_declaration=True,
            )
            issues, _ = TOOL.validate_drawio(drawio)
            self.assertNotIn(
                "routing.node-risk", {item["code"] for item in issues}
            )
            edge = TOOL.ET.parse(drawio).getroot().find(
                ".//mxCell[@id='edge-source-target']"
            )
            points = edge.findall("./mxGeometry/Array/mxPoint")
            self.assertGreaterEqual(len(points), 3)
            self.assertTrue(any(float(point.get("y")) < 220 for point in points))

    def test_invalid_edge_port_and_offset_are_errors(self):
        data = sample_ir()
        data["edges"][0]["style"] = {
            "source_port": "center",
            "target_offset": 1.5,
        }
        codes = {item["code"] for item in TOOL.validate_ir(data)}
        self.assertTrue({"edge.port", "edge.port-offset"} <= codes)

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

    def test_terraform_import_resolves_resource_data_and_module_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.tf").write_text(
                """
                data "aws_ami" "api" { most_recent = true }
                module "network" { source = "./network" }
                resource "aws_instance" "api" {
                  ami       = data.aws_ami.api.id
                  subnet_id = module.network.private_subnet_id
                }
                """,
                encoding="utf-8",
            )
            data = TOOL.import_terraform(root)
            self.assertEqual(3, len(data["nodes"]))
            self.assertEqual(2, len(data["edges"]))
            self.assertEqual(
                {"data.aws_ami.api", "module.network"},
                {
                    next(
                        node["description"].rsplit(" · ", 1)[-1]
                        for node in data["nodes"] if node["id"] == edge["to"]
                    )
                    for edge in data["edges"]
                },
            )
            self.assertEqual(
                [], [item for item in TOOL.validate_ir(data) if item["level"] == "error"]
            )

    def test_kubernetes_import_connects_ingress_service_workload_and_secret(self):
        resources = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "networking.k8s.io/v1",
                    "kind": "Ingress",
                    "metadata": {"name": "shop", "namespace": "prod"},
                    "spec": {
                        "rules": [{
                            "http": {"paths": [{
                                "backend": {"service": {"name": "api", "port": {"number": 80}}}
                            }]}
                        }]
                    },
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api", "namespace": "prod"},
                    "spec": {"selector": {"app": "api"}},
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api", "namespace": "prod"},
                    "spec": {
                        "replicas": 3,
                        "template": {
                            "metadata": {"labels": {"app": "api"}},
                            "spec": {
                                "containers": [{
                                    "name": "api",
                                    "envFrom": [{"secretRef": {"name": "api-secret"}}],
                                }]
                            },
                        },
                    },
                },
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": "api-secret", "namespace": "prod"},
                    "data": {"password": "must-not-appear"},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifests.json"
            path.write_text(json.dumps(resources), encoding="utf-8")
            data = TOOL.import_kubernetes(path)
            self.assertEqual(4, len(data["nodes"]))
            self.assertEqual({"routes", "selects", "uses"}, {edge["label"] for edge in data["edges"]})
            self.assertNotIn("must-not-appear", json.dumps(data))
            self.assertIn("values redacted", json.dumps(data))
            self.assertEqual(
                [], [item for item in TOOL.validate_ir(data) if item["level"] == "error"]
            )

    def test_github_actions_import_uses_needs_execution_order(self):
        workflow = {
            "name": "Release",
            "on": ["push"],
            "jobs": {
                "test": {"runs-on": "ubuntu-latest", "steps": []},
                "release": {"runs-on": "ubuntu-latest", "needs": "test", "steps": []},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(workflow), encoding="utf-8")
            data = TOOL.import_github_actions(path)
            self.assertEqual(2, len(data["nodes"]))
            self.assertEqual("needs", data["edges"][0]["label"])
            self.assertIn("-job-test-before-", data["edges"][0]["id"])

    def test_github_actions_import_links_reusable_workflow_jobs(self):
        workflow = {
            "name": "Delegated release",
            "jobs": {
                "deploy": {
                    "uses": "example/platform/.github/workflows/deploy.yml@v2"
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(workflow), encoding="utf-8")
            data = TOOL.import_github_actions(path)
            self.assertEqual(2, len(data["nodes"]))
            self.assertEqual("calls", data["edges"][0]["label"])
            self.assertIn(
                "example/platform/.github/workflows/deploy.yml@v2",
                {node["description"] for node in data["nodes"]},
            )

    def test_gitlab_ci_import_builds_stage_and_explicit_needs_edges(self):
        pipeline = {
            "stages": ["build", "test", "deploy"],
            "build": {"stage": "build", "script": ["make"]},
            "test": {"stage": "test", "script": ["make test"]},
            "deploy": {"stage": "deploy", "needs": [{"job": "test"}], "script": ["ship"]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gitlab.json"
            path.write_text(json.dumps(pipeline), encoding="utf-8")
            data = TOOL.import_gitlab_ci(path)
            self.assertEqual(3, len(data["nodes"]))
            self.assertEqual({"stage", "needs"}, {edge["label"] for edge in data["edges"]})
            self.assertEqual(
                [], [item for item in TOOL.validate_ir(data) if item["level"] == "error"]
            )

    def test_architecture_diff_ignores_layout_and_reports_semantic_drift(self):
        baseline = sample_ir()
        candidate = sample_ir()
        candidate["nodes"][0]["position"] = {"x": 800, "y": 500}
        no_drift = TOOL.architecture_diff(baseline, candidate)
        self.assertFalse(no_drift["drift"])
        candidate["nodes"][1]["label"] = "Public API"
        candidate["nodes"].append({
            "id": "worker", "label": "Worker", "kind": "service", "group": "core",
        })
        candidate["edges"].append({
            "id": "api-worker", "from": "api", "to": "worker", "kind": "async",
        })
        report = TOOL.architecture_diff(baseline, candidate)
        self.assertTrue(report["drift"])
        self.assertEqual(2, report["summary"]["added"])
        self.assertEqual(1, report["summary"]["changed"])
        drift = TOOL.drift_diagram(baseline, candidate, report)
        self.assertEqual(
            [], [item for item in TOOL.validate_ir(drift) if item["level"] == "error"]
        )
        api = next(node for node in drift["pages"][0]["nodes"] if node["id"] == "api")
        worker = next(node for node in drift["pages"][0]["nodes"] if node["id"] == "worker")
        self.assertEqual("#fff2cc", api["style"]["fill"])
        self.assertEqual("#d9f0d3", worker["style"]["fill"])

    def test_infrastructure_importer_fixture_corpus_is_deterministic_and_strict(self):
        corpus = json.loads(
            (ROOT / "tests/fixtures/importers/corpus.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {"terraform", "kubernetes", "github-actions", "gitlab-ci"}, set(corpus)
        )
        self.assertTrue(all(len(cases) >= 5 for cases in corpus.values()))
        for source_type, cases in corpus.items():
            for case in cases:
                with self.subTest(source_type=source_type, case=case["name"]):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        if source_type == "terraform":
                            (root / "main.tf").write_text(
                                case["source"], encoding="utf-8"
                            )
                        elif source_type == "github-actions":
                            workflows = root / ".github" / "workflows"
                            workflows.mkdir(parents=True)
                            (workflows / "workflow.json").write_text(
                                json.dumps(case["source"]), encoding="utf-8"
                            )
                        elif source_type == "gitlab-ci":
                            (root / ".gitlab-ci.json").write_text(
                                json.dumps(case["source"]), encoding="utf-8"
                            )
                        else:
                            (root / "manifest.json").write_text(
                                json.dumps(case["source"]), encoding="utf-8"
                            )
                        data = TOOL.import_source(root, source_type)
                        self.assertEqual(case["nodes"], len(data["nodes"]))
                        self.assertEqual(case["edges"], len(data["edges"]))
                        self.assertEqual([], TOOL.validate_ir(data))
                        first = TOOL.ET.tostring(TOOL.compile_drawio(data).getroot())
                        second = TOOL.ET.tostring(TOOL.compile_drawio(data).getroot())
                        self.assertEqual(first, second)

    def test_legacy_importer_fixture_corpus_is_deterministic_and_strict(self):
        corpus = json.loads(
            (ROOT / "tests/fixtures/importers/legacy-corpus.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {"python", "typescript", "openapi", "sql", "compose"}, set(corpus)
        )
        self.assertTrue(all(len(cases) >= 5 for cases in corpus.values()))
        for source_type, cases in corpus.items():
            for case in cases:
                with self.subTest(source_type=source_type, case=case["name"]):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        if source_type in {"python", "typescript"}:
                            for relative, content in case["files"].items():
                                path = root / relative
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_text(content, encoding="utf-8")
                            source_path = root
                        elif source_type == "sql":
                            source_path = root / "schema.sql"
                            source_path.write_text(case["source"], encoding="utf-8")
                        else:
                            source_path = root / f"{source_type}.json"
                            source_path.write_text(
                                json.dumps(case["source"]), encoding="utf-8"
                            )
                        data = TOOL.import_source(source_path, source_type)
                        self.assertEqual(case["nodes"], len(data["nodes"]))
                        self.assertEqual(case["edges"], len(data["edges"]))
                        self.assertEqual([], TOOL.validate_ir(data))
                        first = TOOL.ET.tostring(TOOL.compile_drawio(data).getroot())
                        second = TOOL.ET.tostring(TOOL.compile_drawio(data).getroot())
                        self.assertEqual(first, second)

    def test_directory_importers_enforce_explicit_file_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.tf").write_text(
                'resource "aws_vpc" "main" {}\n', encoding="utf-8"
            )
            (root / "data.tf").write_text(
                'data "aws_region" "current" {}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "raise --max-files"):
                TOOL.import_terraform(root, max_files=1)

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
        self.assertEqual(TOOL.CARDINALITY_MARKERS, registry["edge_markers"])

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

    def test_erd_model_preserves_fields_and_cardinalities(self):
        source = json.loads(
            (
                ROOT
                / "skills/drawio-diagram-engineer/assets/example.erd.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual([], TOOL.validate_erd(source))
        diagram_ir = TOOL.erd_to_ir(source)
        entities = {node["id"]: node for node in diagram_ir["nodes"]}
        self.assertEqual("entity", entities["orders"]["kind"])
        self.assertTrue(
            any(field.get("foreign_key") for field in entities["orders"]["fields"])
        )
        relationship = next(
            edge for edge in diagram_ir["edges"] if edge["id"] == "customer-orders"
        )
        self.assertEqual("one", relationship["style"]["start_cardinality"])
        self.assertEqual(
            "zero-or-many", relationship["style"]["end_cardinality"]
        )
        self.assertEqual([], [
            item for item in TOOL.validate_ir(diagram_ir)
            if item["level"] == "error"
        ])
        self.assertEqual(diagram_ir, TOOL.erd_to_ir(source))
        self.assertEqual(
            TOOL.ET.tostring(TOOL.compile_drawio(diagram_ir).getroot()),
            TOOL.ET.tostring(TOOL.compile_drawio(TOOL.erd_to_ir(source)).getroot()),
        )

    def test_sql_ddl_to_erd_extracts_keys_and_types(self):
        source = TOOL.sql_to_erd(
            """
            CREATE TABLE customers (
              id UUID PRIMARY KEY,
              email VARCHAR(255) NOT NULL UNIQUE
            );
            CREATE TABLE orders (
              id UUID PRIMARY KEY,
              customer_id UUID NOT NULL REFERENCES customers(id),
              total NUMERIC(12,2) NOT NULL
            );
            """,
            "Orders",
        )
        self.assertEqual([], TOOL.validate_erd(source))
        entities = {entity["id"]: entity for entity in source["entities"]}
        customer_id = next(
            field
            for field in entities["orders"]["fields"]
            if field["name"] == "customer_id"
        )
        self.assertTrue(customer_id["foreign_key"])
        self.assertFalse(customer_id["nullable"])
        self.assertEqual("customers", source["relationships"][0]["from"])

    def test_sql_ddl_to_erd_supports_alter_table_foreign_keys(self):
        source = TOOL.sql_to_erd(
            """
            CREATE TABLE teams (id BIGINT PRIMARY KEY);
            CREATE TABLE members (
              id BIGINT PRIMARY KEY,
              team_id BIGINT NOT NULL
            );
            ALTER TABLE members ADD CONSTRAINT members_team_fk
              FOREIGN KEY (team_id) REFERENCES teams(id);
            """
        )
        self.assertEqual([], TOOL.validate_erd(source))
        relationship = source["relationships"][0]
        self.assertEqual("teams", relationship["from"])
        self.assertEqual(["team_id"], relationship["to_fields"])

    def test_erd_reports_relationship_type_mismatch(self):
        source = {
            "version": "1",
            "erd": {"title": "Mismatch"},
            "entities": [
                {
                    "id": "parents",
                    "label": "parents",
                    "fields": [
                        {
                            "name": "id",
                            "type": "uuid",
                            "primary_key": True,
                            "nullable": False,
                        }
                    ],
                },
                {
                    "id": "children",
                    "label": "children",
                    "fields": [
                        {
                            "name": "id",
                            "type": "uuid",
                            "primary_key": True,
                            "nullable": False,
                        },
                        {"name": "parent_id", "type": "integer"},
                    ],
                },
            ],
            "relationships": [
                {
                    "id": "parent-children",
                    "from": "parents",
                    "to": "children",
                    "from_fields": ["id"],
                    "to_fields": ["parent_id"],
                    "from_cardinality": "one",
                    "to_cardinality": "zero-or-many",
                }
            ],
        }
        codes = {item["code"] for item in TOOL.validate_erd(source)}
        self.assertIn("erd.type-mismatch", codes)

    def test_erd_supports_self_referencing_relationships(self):
        source = {
            "version": "1",
            "erd": {"title": "Hierarchy"},
            "entities": [
                {
                    "id": "categories",
                    "label": "categories",
                    "fields": [
                        {
                            "name": "id",
                            "type": "uuid",
                            "primary_key": True,
                            "nullable": False,
                        },
                        {
                            "name": "parent_id",
                            "type": "uuid",
                            "foreign_key": True,
                            "nullable": True,
                        },
                    ],
                }
            ],
            "relationships": [
                {
                    "id": "category-parent",
                    "from": "categories",
                    "to": "categories",
                    "from_fields": ["id"],
                    "to_fields": ["parent_id"],
                    "from_cardinality": "zero-or-one",
                    "to_cardinality": "zero-or-many",
                    "label": "parent",
                }
            ],
        }
        diagram_ir = TOOL.erd_to_ir(source)
        self.assertEqual([], [
            item for item in TOOL.validate_ir(diagram_ir)
            if item["level"] == "error"
        ])
        polyline = TOOL.compile_svg(diagram_ir).getroot().find("polyline")
        self.assertGreaterEqual(len(polyline.get("points", "").split()), 5)

    def test_ha_model_generates_failure_domain_and_failover_views(self):
        source = json.loads(
            (
                ROOT
                / "skills/drawio-diagram-engineer/assets/example.ha.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual([], TOOL.validate_ha(source))
        diagram_ir = TOOL.ha_to_ir(source)
        pages = {page["id"]: page for page in diagram_ir["pages"]}
        self.assertEqual({"topology", "failover"}, set(pages))
        self.assertEqual(3, len(pages["topology"]["groups"]))
        promote = next(
            edge for edge in pages["failover"]["edges"]
            if edge["id"] == "database-az-failure-promote"
        )
        self.assertIn("RTO 60s", promote["label"])
        self.assertEqual([], [
            item for item in TOOL.validate_ir(diagram_ir)
            if item["level"] == "error"
        ])
        self.assertEqual(diagram_ir, TOOL.ha_to_ir(source))
        self.assertEqual(
            TOOL.ET.tostring(TOOL.compile_drawio(diagram_ir).getroot()),
            TOOL.ET.tostring(TOOL.compile_drawio(TOOL.ha_to_ir(source)).getroot()),
        )

    def test_ha_rejects_failover_inside_same_domain(self):
        source = json.loads(
            (
                ROOT
                / "skills/drawio-diagram-engineer/assets/example.ha.json"
            ).read_text(encoding="utf-8")
        )
        source["components"][-1]["domain"] = "az-a"
        codes = {item["code"] for item in TOOL.validate_ha(source)}
        self.assertIn("ha.failover.domain", codes)

    def test_ha_warns_when_objectives_and_failover_replication_are_missing(self):
        source = json.loads(
            (
                ROOT
                / "skills/drawio-diagram-engineer/assets/example.ha.json"
            ).read_text(encoding="utf-8")
        )
        for objective in ("availability", "rto", "rpo"):
            source["ha"].pop(objective)
        source["links"] = [
            link for link in source["links"] if link["id"] != "db-replication"
        ]
        codes = {item["code"] for item in TOOL.validate_ha(source)}
        self.assertTrue(
            {
                "ha.availability",
                "ha.rto",
                "ha.rpo",
                "ha.stateful-replication",
                "ha.failover-replication",
            } <= codes
        )


if __name__ == "__main__":
    unittest.main()
