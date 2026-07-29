import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/drawio-diagram-engineer"


class SkillContractTests(unittest.TestCase):
    def test_skill_frontmatter_has_only_portable_trigger_fields(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match)
        keys = {
            line.split(":", 1)[0]
            for line in match.group(1).splitlines()
            if ":" in line and not line.startswith((" ", "\t"))
        }
        self.assertEqual({"name", "description"}, keys)
        self.assertIn("name: drawio-diagram-engineer", match.group(1))

    def test_openai_metadata_names_the_skill_in_default_prompt(self):
        metadata = (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$drawio-diagram-engineer", metadata)

    def test_skill_references_and_assets_exist(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
        for link in links:
            if "://" not in link:
                self.assertTrue((SKILL / link).exists(), link)

    def test_machine_readable_ir_schema_is_json(self):
        for filename in (
            "diagram-ir.schema.json",
            "blueprint.schema.json",
            "theme-pack.schema.json",
            "erd.schema.json",
            "ha.schema.json",
            "drift-report.schema.json",
            "bundle.schema.json",
            "security-report.schema.json",
            "migration-report.schema.json",
            "export-report.schema.json",
            "extraction-report.schema.json",
            "review-site.schema.json",
            "review-annotations.schema.json",
            "architecture-policy.schema.json",
            "policy-report.schema.json",
            "ownership.schema.json",
            "ownership-report.schema.json",
            "github-checks.schema.json",
            "review-attestation.schema.json",
            "policy-tests.schema.json",
            "policy-test-report.schema.json",
            "approval-ledger.schema.json",
            "evidence-catalog.schema.json",
            "governance-trends.schema.json",
            "rule-provider-request.schema.json",
            "rule-provider-result.schema.json",
            "rule-provider-report.schema.json",
            "review-trust.schema.json",
            "delegated-approval-report.schema.json",
            "transparency-log.schema.json",
            "architecture-portal.schema.json",
            "governance-metrics.schema.json",
            "structurizr-adapter.schema.json",
            "adr-adapter.schema.json",
        ):
            schema = SKILL / f"references/{filename}"
            self.assertIn('"$schema"', schema.read_text(encoding="utf-8"))

    def test_shape_registry_and_theme_pack_are_machine_readable(self):
        shape_registry = SKILL / "assets/shape-registry.json"
        theme = SKILL / "assets/themes/corporate.json"
        self.assertIn('"Apache-2.0"', shape_registry.read_text(encoding="utf-8"))
        self.assertIn('"tokens"', theme.read_text(encoding="utf-8"))

    def test_bundle_v1_security_artifact_is_additive_for_v09_compatibility(self):
        schema = json.loads(
            (SKILL / "references/bundle.schema.json").read_text(encoding="utf-8")
        )
        artifacts = schema["properties"]["artifacts"]
        self.assertIn("security", artifacts["properties"])
        self.assertNotIn("security", artifacts["required"])

    def test_skill_distribution_includes_its_license(self):
        license_text = (SKILL / "LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0", license_text)

    def test_cli_reference_covers_every_public_command(self):
        reference = (SKILL / "references/cli.md").read_text(encoding="utf-8")
        commands = {
            "audit",
            "blueprint",
            "build",
            "compile",
            "diff",
            "doctor",
            "erd",
            "extract",
            "ha",
            "import",
            "init",
            "inspect",
            "migrate",
            "merge-annotations",
            "policy-test",
            "patch",
            "preview",
            "publish",
            "render",
            "security",
            "validate",
            "verify-export",
            "attest-review",
            "verify-review-attestation",
            "record-approval",
            "verify-approval-ledger",
            "catalog-reviews",
            "governance-trends",
            "rule-provider-request",
            "verify-rule-provider-result",
            "verify-delegated-approvals",
            "transparency-log",
            "verify-transparency-log",
            "catalog-portal",
            "export-governance-metrics",
            "import-structurizr",
            "export-structurizr",
            "import-adrs",
            "export-adrs",
        }
        for command in commands:
            self.assertRegex(reference, rf"\b{re.escape(command)}\b", command)

    def test_github_pages_recipe_pins_actions_and_retains_revision_artifact(self):
        workflow = (
            SKILL / "assets/github-pages-workflow.yml"
        ).read_text(encoding="utf-8")
        action_references = re.findall(r"uses:\s*[^@\s]+@([^\s]+)", workflow)
        self.assertGreaterEqual(len(action_references), 7)
        self.assertTrue(
            all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_references)
        )
        self.assertIn("diagram-review-${{ github.sha }}", workflow)
        self.assertIn("overwrite: false", workflow)
        self.assertIn("reports/findings.sarif", workflow)

    def test_desktop_release_lock_is_complete_and_valid(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/desktop_lock.py"), "validate"],
            text=True,
            capture_output=True,
            check=True,
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["valid"])
        self.assertEqual(
            ["linux-x64", "macos-universal", "windows-x64"],
            report["platforms"],
        )


if __name__ == "__main__":
    unittest.main()
