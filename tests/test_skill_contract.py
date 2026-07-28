import re
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
        ):
            schema = SKILL / f"references/{filename}"
            self.assertIn('"$schema"', schema.read_text(encoding="utf-8"))

    def test_shape_registry_and_theme_pack_are_machine_readable(self):
        shape_registry = SKILL / "assets/shape-registry.json"
        theme = SKILL / "assets/themes/corporate.json"
        self.assertIn('"Apache-2.0"', shape_registry.read_text(encoding="utf-8"))
        self.assertIn('"tokens"', theme.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
