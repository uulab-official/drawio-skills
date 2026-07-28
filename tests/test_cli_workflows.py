import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/drawio-diagram-engineer/scripts/drawio_tool.py"
ASSETS = ROOT / "skills/drawio-diagram-engineer/assets"


def run_tool(*arguments):
    return subprocess.run(
        [sys.executable, str(TOOL), *map(str, arguments)],
        text=True,
        capture_output=True,
        check=True,
    )


class CliWorkflowTests(unittest.TestCase):
    def test_openapi_to_ir_to_drawio_to_preview(self):
        openapi = {
            "openapi": "3.1.0",
            "info": {"title": "Orders"},
            "paths": {
                "/orders": {
                    "post": {
                        "operationId": "createOrder",
                        "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}}},
                    }
                }
            },
            "components": {"schemas": {"Order": {"properties": {"id": {"type": "string"}}}}},
        }
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = temp / "openapi.json"
            ir = temp / "api.diagram.json"
            drawio = temp / "api.drawio"
            preview = temp / "api.svg"
            source.write_text(json.dumps(openapi), encoding="utf-8")
            run_tool("import", source, "--type", "openapi", "-o", ir)
            run_tool("compile", ir, "-o", drawio)
            run_tool("validate", drawio, "--strict")
            run_tool("preview", ir, "-o", preview)
            self.assertEqual("mxfile", ET.parse(drawio).getroot().tag)
            self.assertEqual("svg", ET.parse(preview).getroot().tag.rsplit("}", 1)[-1])

    def test_verify_export_cli_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            svg = temp / "diagram.svg"
            report = temp / "export-report.json"
            svg.write_text(
                '<svg width="320" height="180"><g><rect width="10" height="10"/></g></svg>',
                encoding="utf-8",
            )
            run_tool("verify-export", svg, "-o", report)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(payload["passed"])
            self.assertEqual(
                {"width": 320.0, "height": 180.0},
                payload["dimensions"],
            )

    def test_patch_to_drawio_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            updated = temp / "updated.json"
            drawio = temp / "updated.drawio"
            run_tool(
                "patch",
                ASSETS / "example.architecture.json",
                ASSETS / "example.patch.json",
                "-o",
                updated,
            )
            run_tool("compile", updated, "-o", drawio)
            run_tool("validate", drawio, "--strict")
            patched = json.loads(updated.read_text(encoding="utf-8"))
            api = next(node for node in patched["nodes"] if node["id"] == "api")
            self.assertEqual({"x": 420, "y": 240}, api["position"])

    def test_multi_page_example_compiles_with_two_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            drawio = Path(directory) / "multi.drawio"
            run_tool("compile", ASSETS / "example.multipage.json", "-o", drawio)
            run_tool("validate", drawio, "--strict")
            self.assertEqual(2, len(ET.parse(drawio).getroot().findall("diagram")))

    def test_blueprint_generates_drawio_ir_and_page_previews(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            drawio = temp / "blueprint.drawio"
            diagram_ir = temp / "blueprint.diagram.json"
            previews = temp / "previews"
            run_tool(
                "blueprint",
                ASSETS / "example.blueprint.json",
                "-o",
                drawio,
                "--ir-output",
                diagram_ir,
                "--preview-dir",
                previews,
                "--strict",
            )
            self.assertEqual(6, len(ET.parse(drawio).getroot().findall("diagram")))
            self.assertEqual(
                {
                    "context.svg",
                    "logical.svg",
                    "data.svg",
                    "deployment.svg",
                    "security.svg",
                    "decisions.svg",
                },
                {path.name for path in previews.glob("*.svg")},
            )
            self.assertEqual(6, len(json.loads(diagram_ir.read_text(encoding="utf-8"))["pages"]))

    def test_theme_pack_and_audit_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            drawio = temp / "themed.drawio"
            report = temp / "audit.json"
            previews = temp / "previews"
            theme = ASSETS / "themes/corporate.json"
            run_tool(
                "compile",
                ASSETS / "example.architecture.json",
                "-o",
                drawio,
                "--theme-file",
                theme,
            )
            run_tool("validate", drawio, "--strict")
            run_tool(
                "audit",
                ASSETS / "example.blueprint.json",
                "-o",
                report,
                "--preview-dir",
                previews,
                "--theme-file",
                theme,
                "--strict",
            )
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertGreaterEqual(payload["score"], 90)
            self.assertEqual(6, payload["summary"]["pages"])
            self.assertEqual("required", payload["visual_review"]["status"])
            self.assertEqual(6, len(payload["visual_review"]["previews"]))

    def test_erd_generates_editable_crows_foot_diagram(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            drawio = temp / "commerce-erd.drawio"
            diagram_ir = temp / "commerce-erd.json"
            previews = temp / "previews"
            run_tool(
                "erd",
                ASSETS / "example.erd.json",
                "-o",
                drawio,
                "--ir-output",
                diagram_ir,
                "--preview-dir",
                previews,
                "--theme-file",
                ASSETS / "themes/corporate.json",
                "--strict",
            )
            run_tool("validate", drawio, "--strict")
            xml = drawio.read_text(encoding="utf-8")
            self.assertIn("ERzeroToMany", xml)
            self.assertIn("ERmandOne", xml)
            self.assertIn("PK FK", xml)
            self.assertTrue((previews / "main.svg").exists())

    def test_ha_generates_topology_and_failover_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            drawio = temp / "checkout-ha.drawio"
            diagram_ir = temp / "checkout-ha.json"
            previews = temp / "previews"
            run_tool(
                "ha",
                ASSETS / "example.ha.json",
                "-o",
                drawio,
                "--ir-output",
                diagram_ir,
                "--preview-dir",
                previews,
                "--theme-file",
                ASSETS / "themes/corporate.json",
                "--strict",
            )
            run_tool("validate", drawio, "--strict")
            pages = ET.parse(drawio).getroot().findall("diagram")
            self.assertEqual(2, len(pages))
            self.assertEqual(
                {"topology.svg", "failover.svg"},
                {path.name for path in previews.glob("*.svg")},
            )

    def test_sql_ddl_can_compile_directly_to_erd(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            sql = temp / "schema.sql"
            drawio = temp / "schema.drawio"
            sql.write_text(
                """
                CREATE TABLE accounts (
                  id UUID PRIMARY KEY,
                  email VARCHAR(255) NOT NULL UNIQUE
                );
                CREATE TABLE sessions (
                  id UUID PRIMARY KEY,
                  account_id UUID NOT NULL REFERENCES accounts(id)
                );
                """,
                encoding="utf-8",
            )
            run_tool(
                "erd",
                sql,
                "-o",
                drawio,
                "--title",
                "Identity Database",
                "--strict",
            )
            run_tool("validate", drawio, "--strict")
            self.assertIn("ERzeroToMany", drawio.read_text(encoding="utf-8"))

    def test_infrastructure_and_pipeline_importers_compile_through_cli(self):
        corpus = json.loads(
            (ROOT / "tests/fixtures/importers/corpus.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            for source_type in (
                "terraform", "kubernetes", "github-actions", "gitlab-ci",
            ):
                case = corpus[source_type][0]
                project = temp / source_type
                project.mkdir()
                if source_type == "terraform":
                    (project / "main.tf").write_text(case["source"], encoding="utf-8")
                elif source_type == "github-actions":
                    workflows = project / ".github" / "workflows"
                    workflows.mkdir(parents=True)
                    (workflows / "workflow.json").write_text(
                        json.dumps(case["source"]), encoding="utf-8"
                    )
                elif source_type == "gitlab-ci":
                    (project / ".gitlab-ci.json").write_text(
                        json.dumps(case["source"]), encoding="utf-8"
                    )
                else:
                    (project / "manifest.json").write_text(
                        json.dumps(case["source"]), encoding="utf-8"
                    )
                ir = temp / f"{source_type}.json"
                drawio = temp / f"{source_type}.drawio"
                run_tool(
                    "import", project, "--type", source_type, "-o", ir
                )
                run_tool("compile", ir, "-o", drawio)
                run_tool("validate", drawio, "--strict")

    def test_diff_generates_machine_report_editable_view_and_preview(self):
        baseline = {
            "version": "1",
            "diagram": {"title": "Payments", "direction": "LR", "theme": "colorblind"},
            "nodes": [
                {"id": "api", "label": "API", "kind": "service"},
                {"id": "db", "label": "DB", "kind": "database"},
            ],
            "edges": [{"id": "api-db", "from": "api", "to": "db", "kind": "data"}],
            "groups": [],
        }
        candidate = json.loads(json.dumps(baseline))
        candidate["nodes"][0]["label"] = "Payments API"
        candidate["nodes"].append({"id": "queue", "label": "Queue", "kind": "queue"})
        candidate["edges"].append({
            "id": "api-queue", "from": "api", "to": "queue", "kind": "async",
        })
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            before = temp / "before.json"
            after = temp / "after.json"
            report = temp / "drift.json"
            drawio = temp / "drift.drawio"
            previews = temp / "previews"
            before.write_text(json.dumps(baseline), encoding="utf-8")
            after.write_text(json.dumps(candidate), encoding="utf-8")
            run_tool(
                "diff", before, after, "-o", report,
                "--diagram-output", drawio, "--preview-dir", previews,
            )
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(payload["drift"])
            self.assertEqual(3, payload["summary"]["total"])
            self.assertTrue((previews / "main.svg").exists())
            run_tool("validate", drawio, "--strict")
            completed = subprocess.run(
                [
                    sys.executable, str(TOOL), "diff", str(before), str(after),
                    "-o", str(temp / "gated-drift.json"), "--fail-on-drift",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(5, completed.returncode)

    def test_routing_example_compiles_with_ports_and_editable_waypoints(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            drawio = temp / "routing.drawio"
            report = temp / "routing.audit.json"
            previews = temp / "previews"
            run_tool(
                "compile", ASSETS / "example.routing.json", "-o", drawio
            )
            run_tool("validate", drawio, "--strict")
            run_tool(
                "audit", ASSETS / "example.routing.json",
                "-o", report, "--preview-dir", previews, "--strict",
            )
            root = ET.parse(drawio).getroot()
            gateway_edges = [
                edge for edge in root.findall(".//mxCell[@edge='1']")
                if edge.get("source") == "node-gateway"
            ]
            offsets = {
                token.split("=", 1)[1]
                for edge in gateway_edges
                for token in edge.get("style", "").split(";")
                if token.startswith("exitY=")
            }
            self.assertEqual(3, len(offsets))
            self.assertTrue(any(
                edge.findall("./mxGeometry/Array/mxPoint")
                for edge in gateway_edges
            ))
            self.assertEqual(
                100, json.loads(report.read_text(encoding="utf-8"))["score"]
            )


if __name__ == "__main__":
    unittest.main()
