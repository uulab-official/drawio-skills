import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/drawio-diagram-engineer/scripts/drawio_tool.py"
ASSETS = ROOT / "skills/drawio-diagram-engineer/assets"
INSTALLER = ROOT / "scripts/install_skill.py"
PACKAGER = ROOT / "scripts/package_skill.py"


def run(*arguments, check=True):
    return subprocess.run(
        [sys.executable, *map(str, arguments)],
        text=True,
        capture_output=True,
        check=check,
    )


class UserExperienceTests(unittest.TestCase):
    def test_doctor_reports_core_ready_and_optional_capabilities(self):
        completed = run(TOOL, "doctor", "--format", "json")
        report = json.loads(completed.stdout)
        self.assertTrue(report["ready"])
        self.assertTrue(report["capabilities"]["editable_drawio"])
        self.assertIn("desktop_export", report["capabilities"])

    def test_init_refuses_accidental_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "architecture.json"
            run(TOOL, "init", "architecture", "-o", output)
            completed = run(TOOL, "init", "architecture", "-o", output, check=False)
            self.assertEqual(2, completed.returncode)
            self.assertIn("already exists", completed.stderr)

    def test_every_starter_profile_can_be_initialized(self):
        profiles = (
            "architecture",
            "blueprint",
            "erd",
            "ha",
            "routing",
            "terraform",
            "kubernetes",
            "github-actions",
            "gitlab-ci",
        )
        with tempfile.TemporaryDirectory() as directory:
            for profile in profiles:
                output = Path(directory) / f"{profile}.starter"
                run(TOOL, "init", profile, "-o", output)
                self.assertGreater(output.stat().st_size, 0, profile)

    def test_build_creates_complete_strict_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            completed = run(
                TOOL,
                "build",
                ASSETS / "example.blueprint.json",
                "-o",
                output,
                "--strict",
            )
            result = json.loads(completed.stdout)
            manifest = json.loads((output / "bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(100, result["score"])
            self.assertEqual("drawio-diagram-bundle/v1", manifest["format"])
            self.assertFalse(manifest["source"]["included"])
            self.assertTrue((output / manifest["artifacts"]["drawio"]).is_file())
            self.assertEqual(6, len(manifest["artifacts"]["previews"]))

    def test_build_auto_selects_crows_foot_erd_for_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = temp / "schema.sql"
            output = temp / "bundle"
            source.write_text(
                """
                CREATE TABLE accounts (id UUID PRIMARY KEY);
                CREATE TABLE sessions (
                  id UUID PRIMARY KEY,
                  account_id UUID NOT NULL REFERENCES accounts(id)
                );
                """,
                encoding="utf-8",
            )
            run(TOOL, "build", source, "-o", output, "--strict")
            manifest = json.loads((output / "bundle.json").read_text(encoding="utf-8"))
            self.assertEqual("erd", manifest["model"])
            self.assertIn(
                "ERmandOne",
                (output / manifest["artifacts"]["drawio"]).read_text(encoding="utf-8"),
            )

    def test_build_creates_strict_ha_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ha"
            run(TOOL, "build", ASSETS / "example.ha.json", "-o", output, "--strict")
            manifest = json.loads((output / "bundle.json").read_text(encoding="utf-8"))
            self.assertEqual("ha", manifest["model"])
            self.assertEqual(
                ["previews/topology.svg", "previews/failover.svg"],
                manifest["artifacts"]["previews"],
            )

    def test_build_force_refuses_unowned_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "important"
            output.mkdir()
            (output / "keep.txt").write_text("user data", encoding="utf-8")
            completed = run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                output,
                "--force",
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertEqual("user data", (output / "keep.txt").read_text(encoding="utf-8"))

    def test_installer_copies_and_self_checks_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "skills"
            completed = run(INSTALLER, "--target", target)
            report = json.loads(completed.stdout)
            installed = target / "drawio-diagram-engineer"
            self.assertTrue(report["ready"])
            self.assertTrue((installed / "SKILL.md").is_file())
            doctor = run(
                installed / "scripts/drawio_tool.py",
                "doctor",
                "--format",
                "json",
            )
            self.assertTrue(json.loads(doctor.stdout)["ready"])

    def test_installer_symlinks_and_self_checks_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "skills"
            completed = run(INSTALLER, "--target", target, "--mode", "symlink")
            report = json.loads(completed.stdout)
            installed = target / "drawio-diagram-engineer"
            self.assertTrue(report["ready"])
            self.assertTrue(installed.is_symlink())
            self.assertEqual(
                (ROOT / "skills/drawio-diagram-engineer").resolve(),
                installed.resolve(),
            )

    def test_installer_refuses_to_replace_its_source_tree(self):
        completed = run(
            INSTALLER,
            "--target",
            ROOT / "skills",
            "--force",
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("skill source directory", completed.stderr)
        self.assertTrue((ROOT / "skills/drawio-diagram-engineer/SKILL.md").is_file())

    def test_release_zip_is_byte_reproducible_and_has_skill_root(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            run(PACKAGER, "-o", first)
            run(PACKAGER, "-o", second)
            first_digest = hashlib.sha256(first.read_bytes()).hexdigest()
            second_digest = hashlib.sha256(second.read_bytes()).hexdigest()
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(
                f"{first_digest}  {first.name}\n",
                first.with_suffix(".zip.sha256").read_text(encoding="utf-8"),
            )
            import zipfile

            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
            self.assertIn("drawio-diagram-engineer/SKILL.md", names)
            self.assertIn(
                "drawio-diagram-engineer/scripts/drawio_tool.py",
                names,
            )
            self.assertIn("drawio-diagram-engineer/LICENSE.txt", names)


if __name__ == "__main__":
    unittest.main()
