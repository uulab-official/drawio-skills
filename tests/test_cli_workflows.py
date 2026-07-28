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


if __name__ == "__main__":
    unittest.main()
