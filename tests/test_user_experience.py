import hashlib
import json
import shutil
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
AUDITOR = ROOT / "scripts/audit_repository.py"
TAG_VERIFIER = ROOT / "scripts/verify_release_tag.py"


def run(*arguments, check=True):
    return subprocess.run(
        [sys.executable, *map(str, arguments)],
        text=True,
        capture_output=True,
        check=check,
    )


class UserExperienceTests(unittest.TestCase):
    def test_signed_release_tag_verification_contract(self):
        if not shutil.which("ssh-keygen") or not shutil.which("git"):
            self.skipTest("git and ssh-keygen are required")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            repository = temp / "repository"
            repository.mkdir()
            key = temp / "release-signing-key"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                check=True,
            )
            public_key = key.with_suffix(".pub").read_text(encoding="utf-8").strip()
            (repository / ".github").mkdir()
            (repository / ".github/release-signers").write_text(
                f"release@example.com namespaces=\"git\" {public_key}\n",
                encoding="utf-8",
            )
            tool = repository / "skills/drawio-diagram-engineer/scripts"
            tool.mkdir(parents=True)
            (tool / "drawio_tool.py").write_text(
                'VERSION = "1.2.3"\n', encoding="utf-8"
            )
            (repository / "pyproject.toml").write_text(
                '[project]\nversion = "1.2.3"\n', encoding="utf-8"
            )
            (repository / "CHANGELOG.md").write_text(
                "# Changelog\n\n## 1.2.3 — Test\n", encoding="utf-8"
            )
            commands = [
                ["git", "init", "-q", str(repository)],
                ["git", "-C", str(repository), "config", "user.name", "Release Test"],
                ["git", "-C", str(repository), "config", "user.email", "release@example.com"],
                ["git", "-C", str(repository), "add", "."],
                ["git", "-C", str(repository), "commit", "-q", "-m", "release"],
                ["git", "-C", str(repository), "config", "gpg.format", "ssh"],
                ["git", "-C", str(repository), "config", "user.signingkey", str(key)],
                [
                    "git", "-C", str(repository), "tag", "-s", "v1.2.3",
                    "-m", "v1.2.3",
                ],
            ]
            for command in commands:
                subprocess.run(command, check=True)
            verified = run(TAG_VERIFIER, "v1.2.3", "--repo", repository)
            report = json.loads(verified.stdout)
            self.assertTrue(report["passed"])
            self.assertTrue(report["signed"])
            self.assertEqual("release@example.com", report["principal"])
            self.assertTrue(str(report["fingerprint"]).startswith("SHA256:"))

            subprocess.run(
                [
                    "git", "-C", str(repository), "tag", "-a", "v1.2.4",
                    "-m", "v1.2.4",
                ],
                check=True,
            )
            unsigned = run(
                TAG_VERIFIER, "v1.2.4", "--repo", repository, check=False
            )
            self.assertEqual(2, unsigned.returncode)
            self.assertIn(
                "tag.signature",
                {
                    item["code"]
                    for item in json.loads(unsigned.stdout)["findings"]
                },
            )

    def test_repository_dependency_and_workflow_audit_passes(self):
        completed = run(AUDITOR)
        report = json.loads(completed.stdout)
        self.assertTrue(report["passed"])
        self.assertEqual([], report["runtime_dependencies"])
        self.assertEqual(["yaml"], report["optional_dependencies"])
        self.assertEqual([], report["unpinned_actions"])
        self.assertTrue(all(report["release_contracts"].values()))
        self.assertEqual(
            {
                "actions/attest",
                "actions/checkout",
                "actions/setup-python",
                "actions/upload-artifact",
            },
            {item["action"] for item in report["workflow_actions"]},
        )

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
            self.assertTrue((output / manifest["artifacts"]["security"]).is_file())
            security = json.loads((output / "security.json").read_text(encoding="utf-8"))
            self.assertTrue(security["passed"])
            self.assertEqual("example.blueprint.json", security["source"])
            self.assertEqual(6, len(manifest["artifacts"]["previews"]))

    def test_publish_creates_semantic_review_site_and_visual_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review = temp / "review"
            run(
                TOOL,
                "build",
                ASSETS / "example.blueprint.json",
                "-o",
                bundle,
                "--strict",
            )
            (bundle / "architecture.export.json").write_text(
                json.dumps({
                    "format": "drawio-export-report/v1",
                    "source": "architecture.svg",
                    "expected_format": "svg",
                    "detected_format": "svg",
                    "size_bytes": 1024,
                    "passed": True,
                    "findings": [],
                }),
                encoding="utf-8",
            )
            published = run(
                TOOL,
                "publish",
                bundle,
                "-o",
                review,
                "--annotations",
                ASSETS / "example.review-annotations.json",
                "--strict",
            )
            result = json.loads(published.stdout)
            manifest = json.loads(
                (review / "review.json").read_text(encoding="utf-8")
            )
            self.assertEqual("drawio-review-site/v1", manifest["format"])
            self.assertEqual(6, result["pages"])
            self.assertTrue(manifest["status"]["audit"]["passed"])
            self.assertTrue(manifest["status"]["security"]["passed"])
            self.assertTrue(manifest["status"]["extraction"]["lossless"])
            self.assertTrue(manifest["status"]["extraction"]["semantic_match"])
            self.assertEqual("passed", manifest["status"]["exports"]["status"])
            self.assertEqual(1, len(manifest["status"]["exports"]["reports"]))
            self.assertEqual(
                {
                    "pages/context.svg#node-commerce",
                    "pages/data.svg#node-orders-db",
                },
                {item["href"] for item in manifest["annotations"]},
            )
            html_text = (review / "index.html").read_text(encoding="utf-8")
            self.assertIn("Content-Security-Policy", html_text)
            self.assertNotIn("<script", html_text)
            self.assertIn("Semantic element index", html_text)
            self.assertTrue((review / "reports/extraction.json").is_file())

            same_review = temp / "same-review"
            run(
                TOOL,
                "publish",
                bundle,
                "-o",
                same_review,
                "--baseline",
                review,
                "--fail-on-visual-change",
            )
            same_manifest = json.loads(
                (same_review / "review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                "passed",
                same_manifest["status"]["visual_regression"]["status"],
            )
            self.assertEqual(
                6,
                same_manifest["status"]["visual_regression"]["summary"]["unchanged"],
            )

            diagram_path = bundle / "diagram.json"
            diagram = json.loads(diagram_path.read_text(encoding="utf-8"))
            context = next(
                page for page in diagram["pages"] if page["id"] == "context"
            )
            commerce = next(
                node for node in context["nodes"] if node["id"] == "commerce"
            )
            commerce["label"] = "Commerce Platform v2"
            diagram_path.write_text(
                json.dumps(diagram, indent=2) + "\n",
                encoding="utf-8",
            )
            bundle_manifest = json.loads(
                (bundle / "bundle.json").read_text(encoding="utf-8")
            )
            run(
                TOOL,
                "compile",
                diagram_path,
                "-o",
                bundle / bundle_manifest["artifacts"]["drawio"],
            )
            changed_review = temp / "changed-review"
            changed = run(
                TOOL,
                "publish",
                bundle,
                "-o",
                changed_review,
                "--baseline",
                review,
                "--fail-on-visual-change",
                check=False,
            )
            self.assertEqual(7, changed.returncode)
            changed_manifest = json.loads(
                (changed_review / "review.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                changed_manifest["status"]["visual_regression"]["changed"]
            )
            context_visual = next(
                page
                for page in changed_manifest["status"]["visual_regression"]["pages"]
                if page["id"] == "context"
            )
            self.assertEqual("changed", context_visual["status"])

    def test_publish_force_refuses_unowned_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            output = temp / "review"
            output.mkdir()
            (output / "keep.txt").write_text("owned by user", encoding="utf-8")
            run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                bundle,
                "--strict",
            )
            completed = run(
                TOOL,
                "publish",
                bundle,
                "-o",
                output,
                "--force",
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("unrecognized directory", completed.stderr)
            self.assertEqual(
                "owned by user",
                (output / "keep.txt").read_text(encoding="utf-8"),
            )

    def test_review_lifecycle_policy_and_sarif_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            first_review = temp / "first-review"
            current_review = temp / "current-review"
            merged_annotations = temp / "merged-annotations.json"
            run(
                TOOL,
                "build",
                ASSETS / "example.blueprint.json",
                "-o",
                bundle,
                "--strict",
            )
            run(
                TOOL,
                "publish",
                bundle,
                "-o",
                first_review,
                "--annotations",
                ASSETS / "example.review-annotations.json",
                "--strict",
            )
            merged = run(
                TOOL,
                "merge-annotations",
                first_review,
                ASSETS / "example.review-annotation-updates.json",
                "-o",
                merged_annotations,
            )
            merged_result = json.loads(merged.stdout)
            merged_data = json.loads(
                merged_annotations.read_text(encoding="utf-8")
            )
            self.assertEqual(2, merged_result["summary"]["updated"])
            self.assertEqual(
                {"accepted", "resolved"},
                {
                    annotation["status"]
                    for annotation in merged_data["annotations"]
                },
            )

            run(
                TOOL,
                "publish",
                bundle,
                "-o",
                current_review,
                "--carry-review",
                first_review,
                "--annotations",
                ASSETS / "example.review-annotation-updates.json",
                "--baseline",
                first_review,
                "--policy",
                ASSETS / "policies/production-review.json",
                "--fail-on-policy",
                "--strict",
            )
            manifest = json.loads(
                (current_review / "review.json").read_text(encoding="utf-8")
            )
            self.assertEqual("passed", manifest["status"]["policy"]["status"])
            self.assertEqual(2, manifest["status"]["annotations"]["updated"])
            self.assertEqual(0, manifest["status"]["annotations"]["open"])
            self.assertTrue(
                all(
                    annotation["lifecycle"] == "updated"
                    for annotation in manifest["annotations"]
                    if annotation.get("source") == "reviewer"
                )
            )
            policy = json.loads(
                (current_review / "reports/policy.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                "drawio-architecture-policy-report/v1",
                policy["format"],
            )
            self.assertTrue(policy["passed"])
            sarif = json.loads(
                (current_review / "reports/findings.sarif").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("2.1.0", sarif["version"])
            self.assertEqual([], sarif["runs"][0]["results"])
            html_text = (current_review / "index.html").read_text(encoding="utf-8")
            self.assertIn("Architecture policy", html_text)
            self.assertIn("SARIF findings", html_text)
            self.assertIn("og:title", html_text)

    def test_failing_policy_returns_eight_and_emits_sarif(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review = temp / "review"
            run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                bundle,
                "--strict",
            )
            completed = run(
                TOOL,
                "publish",
                bundle,
                "-o",
                review,
                "--policy",
                ASSETS / "policies/production-review.json",
                "--fail-on-policy",
                check=False,
            )
            self.assertEqual(8, completed.returncode)
            policy = json.loads(
                (review / "reports/policy.json").read_text(encoding="utf-8")
            )
            self.assertFalse(policy["passed"])
            sarif = json.loads(
                (review / "reports/findings.sarif").read_text(encoding="utf-8")
            )
            rule_ids = {
                result["ruleId"]
                for result in sarif["runs"][0]["results"]
            }
            self.assertIn("policy.required-views", rule_ids)

    def test_migrate_check_and_write_workflow(self):
        legacy = {
            "title": "Legacy",
            "components": [
                {"id": "client", "label": "Client", "type": "user"},
                {"id": "api", "label": "API", "type": "api"},
            ],
            "connections": [{"source": "client", "target": "api"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            source = temp / "legacy.json"
            output = temp / "diagram.json"
            report = temp / "migration.json"
            source.write_text(json.dumps(legacy), encoding="utf-8")
            check = run(TOOL, "migrate", source, "--check", check=False)
            self.assertEqual(6, check.returncode)
            run(TOOL, "migrate", source, "-o", output, "--report", report)
            migrated = json.loads(output.read_text(encoding="utf-8"))
            migration = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual("1", migrated["version"])
            self.assertTrue(migration["changes_required"])
            self.assertEqual(0, run(TOOL, "migrate", output, "--check").returncode)

    def test_security_command_rejects_unsafe_link(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unsafe.json"
            source.write_text(
                json.dumps({
                    "version": "1",
                    "diagram": {"title": "Unsafe"},
                    "nodes": [
                        {"id": "api", "label": "API", "link": "javascript:alert(1)"}
                    ],
                    "edges": [],
                }),
                encoding="utf-8",
            )
            completed = run(TOOL, "security", source, check=False)
            self.assertEqual(2, completed.returncode)
            report = json.loads(completed.stdout)
            self.assertIn(
                "security.unsafe-link",
                {item["code"] for item in report["findings"]},
            )

    def test_security_command_scans_complete_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle"
            run(TOOL, "build", ASSETS / "example.architecture.json", "-o", output, "--strict")
            completed = run(TOOL, "security", output, "--strict")
            report = json.loads(completed.stdout)
            self.assertTrue(report["passed"])
            self.assertGreaterEqual(len(report["scanned"]), 3)

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
