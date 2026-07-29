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
            self.assertTrue((review / "reports/evidence-catalog.json").is_file())
            self.assertTrue((review / "reports/governance-trends.csv").is_file())
            self.assertTrue((review / "reports/governance.prom").is_file())
            self.assertTrue((review / "reports/governance.otlp.json").is_file())
            self.assertTrue((review / "reports/governance-metrics.json").is_file())
            self.assertTrue((review / "reports/rule-provider-request.json").is_file())
            transparency = run(
                TOOL,
                "verify-transparency-log",
                review / "reports/transparency-log.json",
            )
            self.assertTrue(json.loads(transparency.stdout)["passed"])

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
            self.assertIn("policy.production.required-views", rule_ids)

    def test_composed_policy_exception_ownership_provenance_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            prior_review = temp / "prior-review"
            governed_review = temp / "governed-review"
            revision = "0123456789abcdef0123456789abcdef01234567"
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
                prior_review,
                "--annotations",
                ASSETS / "example.review-annotations.json",
                "--strict",
            )
            run(
                TOOL,
                "publish",
                bundle,
                "-o",
                governed_review,
                "--carry-review",
                prior_review,
                "--annotations",
                ASSETS / "example.governance-annotations.json",
                "--baseline",
                prior_review,
                "--policy",
                ASSETS / "policies/production-review.json",
                "--policy",
                ASSETS / "policies/team-governance.json",
                "--ownership",
                ASSETS / "example.ownership.json",
                "--evaluation-date",
                "2026-07-29",
                "--source-revision",
                revision,
                "--source-repository",
                "uulab/example",
                "--source-url",
                f"https://github.com/uulab/example/commit/{revision}",
                "--public-base-url",
                "https://reviews.example.com/pr-42",
                "--fail-on-policy",
                "--fail-on-unowned-findings",
                "--strict",
            )
            manifest = json.loads(
                (governed_review / "review.json").read_text(encoding="utf-8")
            )
            self.assertEqual(2, len(manifest["policy"]["policies"]))
            governed_rule = next(
                result
                for result in manifest["policy"]["results"]
                if result["key"] == "team-governance/no-open-decisions"
            )
            self.assertTrue(governed_rule["passed"])
            self.assertFalse(governed_rule["compliant"])
            self.assertTrue(governed_rule["waived"])
            exception = manifest["policy"]["exceptions"][0]
            self.assertEqual("applied", exception["status"])
            self.assertEqual(
                ["team-governance/no-open-decisions"],
                exception["applied_to"],
            )
            self.assertTrue(manifest["status"]["ownership"]["passed"])
            self.assertEqual(1, manifest["status"]["ownership"]["assigned"])
            self.assertEqual(revision, manifest["provenance"]["revision"])
            self.assertEqual("scm", manifest["provenance"]["revision_type"])
            self.assertRegex(
                manifest["provenance"]["bundle_sha256"],
                r"^[0-9a-f]{64}$",
            )
            sarif = json.loads(
                (governed_review / "reports/findings.sarif").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(1, len(sarif["runs"][0]["results"]))
            finding = sarif["runs"][0]["results"][0]
            self.assertEqual("review.annotation-open", finding["ruleId"])
            self.assertEqual(
                ["@uulab/platform"],
                finding["properties"]["owners"],
            )
            summary = (
                governed_review / "reports/summary.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "https://reviews.example.com/pr-42/pages/logical.svg#node-events",
                summary,
            )
            self.assertIn("@uulab/platform", summary)
            html_text = (governed_review / "index.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("Artifact provenance", html_text)
            self.assertIn("Finding ownership", html_text)

    def test_expired_exception_fails_policy_and_surfaces_sarif(self):
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
            completed = run(
                TOOL,
                "publish",
                bundle,
                "-o",
                review,
                "--annotations",
                ASSETS / "example.governance-annotations.json",
                "--policy",
                ASSETS / "policies/team-governance.json",
                "--evaluation-date",
                "2027-01-01",
                "--fail-on-policy",
                check=False,
            )
            self.assertEqual(8, completed.returncode)
            policy = json.loads(
                (review / "reports/policy.json").read_text(encoding="utf-8")
            )
            self.assertEqual("expired", policy["exceptions"][0]["status"])
            self.assertGreaterEqual(policy["errors"], 2)
            sarif = json.loads(
                (review / "reports/findings.sarif").read_text(encoding="utf-8")
            )
            rule_ids = {
                result["ruleId"]
                for result in sarif["runs"][0]["results"]
            }
            self.assertIn(
                "policy-exception.team-governance.event-stream-review-window",
                rule_ids,
            )
            self.assertIn(
                "policy.team-governance.no-open-decisions",
                rule_ids,
            )

    def test_unowned_finding_gate_returns_nine(self):
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
            completed = run(
                TOOL,
                "publish",
                bundle,
                "-o",
                review,
                "--annotations",
                ASSETS / "example.governance-annotations.json",
                "--fail-on-unowned-findings",
                check=False,
            )
            self.assertEqual(9, completed.returncode)
            ownership = json.loads(
                (review / "reports/ownership.json").read_text(encoding="utf-8")
            )
            self.assertEqual("not-configured", ownership["status"])
            self.assertEqual(1, ownership["unassigned"])

    def test_codeowners_fallback_preserves_explicit_routes_and_emits_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review = temp / "review"
            ownership_path = temp / "ownership.json"
            revision = "0123456789abcdef0123456789abcdef01234567"
            ownership_path.write_text(
                json.dumps({
                    "format": "drawio-review-ownership/v1",
                    "routes": [{
                        "id": "event-stream",
                        "owners": ["@uulab/platform"],
                        "pages": ["logical"],
                        "cells": ["node-events"],
                    }],
                }),
                encoding="utf-8",
            )
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
                review,
                "--annotations",
                ASSETS / "example.governance-annotations.json",
                "--policy",
                ASSETS / "policies/production-review.json",
                "--ownership",
                ownership_path,
                "--codeowners",
                ASSETS / "example.CODEOWNERS",
                "--source-path",
                "architecture/commerce-platform.json",
                "--source-revision",
                revision,
                "--source-repository",
                "uulab/example",
                "--public-base-url",
                "https://reviews.example.com/pr-42",
                "--github-checks",
                "--fail-on-unowned-findings",
            )
            ownership = json.loads(
                (review / "reports/ownership.json").read_text(encoding="utf-8")
            )
            assignments = {
                item["rule_id"]: item
                for item in ownership["assignments"]
            }
            reviewer = assignments["review.annotation-open"]
            self.assertEqual("routes", reviewer["source"])
            self.assertEqual(["@uulab/platform"], reviewer["owners"])
            policy = assignments["policy.production.approved-baseline"]
            self.assertEqual("codeowners", policy["source"])
            self.assertEqual(
                ["@uulab/architecture", "@uulab/platform"],
                policy["owners"],
            )
            checks = json.loads(
                (review / "reports/github-checks.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("drawio-github-checks/v1", checks["format"])
            self.assertEqual(revision, checks["request"]["head_sha"])
            self.assertEqual(
                "architecture/commerce-platform.json",
                checks["request"]["output"]["annotations"][0]["path"],
            )
            review_bytes = (review / "review.json").read_bytes()
            attestation = json.loads(
                (review / "reports/attestation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                hashlib.sha256(review_bytes).hexdigest(),
                attestation["subject"][0]["digest"]["sha256"],
            )
            self.assertEqual(
                "architecture/commerce-platform.json",
                attestation["predicate"]["source"]["path"],
            )

    def test_policy_test_harness_covers_rules_and_detects_outcome_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            report = temp / "policy-tests.json"
            run(
                TOOL,
                "policy-test",
                ASSETS / "example.policy-tests.json",
                "-o",
                report,
                "--strict",
            )
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(result["gate"]["passed"])
            self.assertEqual(100, result["coverage"]["percent"])
            self.assertEqual(0, result["assertions"]["failed"])
            unchanged = run(
                TOOL,
                "policy-test",
                ASSETS / "example.policy-tests.json",
                "--baseline",
                report,
                "--fail-on-change",
            )
            self.assertEqual(0, unchanged.returncode)
            result["cases"][0]["outcome_fingerprint"] = "0" * 64
            report.write_text(
                json.dumps(result),
                encoding="utf-8",
            )
            changed = run(
                TOOL,
                "policy-test",
                ASSETS / "example.policy-tests.json",
                "--baseline",
                report,
                "--fail-on-change",
                check=False,
            )
            self.assertEqual(10, changed.returncode)

    def test_review_attestation_sign_and_verify_detects_tampering(self):
        if not shutil.which("ssh-keygen"):
            self.skipTest("ssh-keygen is required")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review = temp / "review"
            key = temp / "review-key"
            allowed_signers = temp / "allowed-signers"
            run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                bundle,
                "--strict",
            )
            run(TOOL, "publish", bundle, "-o", review, "--strict")
            subprocess.run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(key),
                ],
                check=True,
            )
            allowed_signers.write_text(
                "review@example.com "
                + key.with_suffix(".pub").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            run(
                TOOL,
                "attest-review",
                review,
                "--signing-key",
                key,
            )
            verified = run(
                TOOL,
                "verify-review-attestation",
                review,
                "--allowed-signers",
                allowed_signers,
                "--identity",
                "review@example.com",
            )
            self.assertTrue(json.loads(verified.stdout)["passed"])
            manifest_path = review / "review.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["title"] = "Tampered review"
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            tampered = run(
                TOOL,
                "verify-review-attestation",
                review,
                "--allowed-signers",
                allowed_signers,
                "--identity",
                "review@example.com",
                check=False,
            )
            self.assertEqual(11, tampered.returncode)
            self.assertFalse(json.loads(tampered.stdout)["passed"])

    def test_signed_approval_ledger_enforces_quorum_and_revocation(self):
        if not shutil.which("ssh-keygen"):
            self.skipTest("ssh-keygen is required")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review = temp / "review"
            ledger = temp / "approvals.json"
            allowed_signers = temp / "allowed-signers"
            run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                bundle,
                "--strict",
            )
            run(TOOL, "publish", bundle, "-o", review, "--strict")
            keys = {}
            signer_lines = []
            for identity in ("architecture@example.com", "security@example.com"):
                key = temp / identity.split("@", 1)[0]
                subprocess.run(
                    [
                        "ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                        "-f", str(key),
                    ],
                    check=True,
                )
                keys[identity] = key
                signer_lines.append(
                    f'{identity} namespaces="drawio-approval" '
                    + key.with_suffix(".pub").read_text(encoding="utf-8")
                )
            allowed_signers.write_text("".join(signer_lines), encoding="utf-8")
            first = run(
                TOOL,
                "record-approval",
                review,
                "--ledger",
                ledger,
                "--identity",
                "architecture@example.com",
                "--role",
                "architecture",
                "--timestamp",
                "2026-07-29T01:00:00Z",
                "--reason",
                "Architecture approved",
                "--signing-key",
                keys["architecture@example.com"],
                "--minimum-approvals",
                "2",
                "--required-role",
                "architecture",
                "--required-role",
                "security",
            )
            first_event = json.loads(first.stdout)["event"]
            self.assertFalse(json.loads(first.stdout)["quorum"]["quorum_met"])
            run(
                TOOL,
                "record-approval",
                review,
                "--ledger",
                ledger,
                "--identity",
                "security@example.com",
                "--role",
                "security",
                "--timestamp",
                "2026-07-29T01:01:00Z",
                "--reason",
                "Security approved",
                "--signing-key",
                keys["security@example.com"],
                "--allowed-signers",
                allowed_signers,
            )
            verified = run(
                TOOL,
                "verify-approval-ledger",
                review,
                "--ledger",
                ledger,
                "--allowed-signers",
                allowed_signers,
            )
            self.assertTrue(json.loads(verified.stdout)["quorum_met"])
            run(
                TOOL,
                "record-approval",
                review,
                "--ledger",
                ledger,
                "--identity",
                "architecture@example.com",
                "--role",
                "architecture",
                "--timestamp",
                "2026-07-29T01:02:00Z",
                "--reason",
                "Architecture changed",
                "--action",
                "revoke",
                "--revokes",
                first_event,
                "--signing-key",
                keys["architecture@example.com"],
                "--allowed-signers",
                allowed_signers,
            )
            revoked = run(
                TOOL,
                "verify-approval-ledger",
                review,
                "--ledger",
                ledger,
                "--allowed-signers",
                allowed_signers,
                check=False,
            )
            self.assertEqual(12, revoked.returncode)
            revoked_report = json.loads(revoked.stdout)
            self.assertTrue(revoked_report["integrity_passed"])
            self.assertFalse(revoked_report["quorum_met"])
            self.assertEqual(1, revoked_report["revoked_approvals"])

    def test_catalog_trends_and_sandboxed_rule_provider_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review_a = temp / "review-a"
            review_b = temp / "review-b"
            catalog = temp / "catalog.json"
            trends = temp / "trends.json"
            trends_csv = temp / "trends.csv"
            request = temp / "provider-request.json"
            result = temp / "provider-result.json"
            provider_report = temp / "provider-report.json"
            run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                bundle,
                "--strict",
            )
            for review, repository, revision in (
                (review_a, "uulab/service-a", "a" * 40),
                (review_b, "uulab/service-b", "b" * 40),
            ):
                run(
                    TOOL,
                    "publish",
                    bundle,
                    "-o",
                    review,
                    "--source-repository",
                    repository,
                    "--source-revision",
                    revision,
                    "--source-path",
                    "architecture/system.json",
                    "--strict",
                )
            run(
                TOOL,
                "catalog-reviews",
                review_a,
                review_b,
                "-o",
                catalog,
            )
            catalog_report = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(2, catalog_report["summary"]["repositories"])
            self.assertEqual(2, catalog_report["summary"]["reviews"])
            run(
                TOOL,
                "governance-trends",
                "--snapshot",
                f"2026-07-28={review_a}",
                "--snapshot",
                f"2026-07-29={review_a}",
                "-o",
                trends,
                "--csv-output",
                trends_csv,
            )
            trend_report = json.loads(trends.read_text(encoding="utf-8"))
            self.assertEqual(2, len(trend_report["snapshots"]))
            self.assertIn("ownership_coverage_percent", trend_report["change"])
            self.assertTrue(trends_csv.read_text(encoding="utf-8").startswith("date,"))
            request_result = run(
                TOOL,
                "rule-provider-request",
                review_a,
                "-o",
                request,
            )
            request_digest = json.loads(request_result.stdout)["request_sha256"]
            result.write_text(
                json.dumps({
                    "format": "drawio-rule-provider-result/v1",
                    "request_sha256": request_digest,
                    "provider": {
                        "id": "organization-guardrails",
                        "version": "1.0.0",
                    },
                    "results": [{
                        "id": "api-owner",
                        "rule_id": "ownership.api",
                        "level": "warning",
                        "passed": False,
                        "message": "Confirm the API owner.",
                        "page": "main",
                        "cell": "api",
                    }],
                }),
                encoding="utf-8",
            )
            run(
                TOOL,
                "verify-rule-provider-result",
                request,
                result,
                "-o",
                provider_report,
            )
            validated = json.loads(provider_report.read_text(encoding="utf-8"))
            self.assertTrue(validated["integrity_passed"])
            self.assertEqual(1, validated["summary"]["warnings"])
            self.assertEqual(
                "provider.organization-guardrails.ownership.api",
                validated["sarif"]["runs"][0]["results"][0]["ruleId"],
            )

    def test_delegated_trust_and_append_only_transparency(self):
        if not shutil.which("ssh-keygen"):
            self.skipTest("ssh-keygen is required")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review = temp / "review"
            ledger = temp / "approvals.json"
            trust_root = temp / "trust"
            trust_root.mkdir()
            run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                bundle,
                "--strict",
            )
            run(TOOL, "publish", bundle, "-o", review, "--strict")
            keys = {}
            combined_lines = []
            delegations = []
            signer_definitions = (
                (
                    "architecture@example.com",
                    "architecture",
                    "architecture-platform",
                    "2026-01-01T00:00:00Z",
                    "2026-07-29T01:00:30Z",
                ),
                (
                    "security@example.com",
                    "security",
                    "security-assurance",
                    "2026-07-29T01:00:30Z",
                    "2027-01-01T00:00:00Z",
                ),
            )
            for index, (
                identity,
                role,
                team,
                valid_from,
                valid_until,
            ) in enumerate(signer_definitions, start=1):
                key = temp / f"reviewer-{index}"
                subprocess.run(
                    [
                        "ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                        "-f", str(key),
                    ],
                    check=True,
                )
                keys[identity] = key
                signer_line = (
                    f'{identity} namespaces="drawio-approval" '
                    + key.with_suffix(".pub").read_text(encoding="utf-8")
                )
                combined_lines.append(signer_line)
                signers = trust_root / f"epoch-{index}.allowed-signers"
                signers.write_text(signer_line, encoding="utf-8")
                delegations.append({
                    "id": f"epoch-{index}",
                    "principals": [identity],
                    "roles": [role],
                    "teams": [team],
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                    "allowed_signers": signers.name,
                    "allowed_signers_sha256": hashlib.sha256(
                        signers.read_bytes()
                    ).hexdigest(),
                })
            combined = temp / "combined.allowed-signers"
            combined.write_text("".join(combined_lines), encoding="utf-8")
            first = run(
                TOOL,
                "record-approval",
                review,
                "--ledger",
                ledger,
                "--identity",
                "architecture@example.com",
                "--role",
                "architecture",
                "--timestamp",
                "2026-07-29T01:00:00Z",
                "--reason",
                "Architecture approved",
                "--signing-key",
                keys["architecture@example.com"],
                "--minimum-approvals",
                "2",
                "--required-role",
                "architecture",
                "--required-role",
                "security",
            )
            self.assertFalse(json.loads(first.stdout)["quorum"]["quorum_met"])
            run(
                TOOL,
                "record-approval",
                review,
                "--ledger",
                ledger,
                "--identity",
                "security@example.com",
                "--role",
                "security",
                "--timestamp",
                "2026-07-29T01:01:00Z",
                "--reason",
                "Security approved",
                "--signing-key",
                keys["security@example.com"],
                "--allowed-signers",
                combined,
            )
            trust_policy = temp / "review-trust.json"
            trust_policy.write_text(
                json.dumps({
                    "format": "drawio-review-trust/v1",
                    "organization": "UULAB",
                    "requirements": {
                        "minimum_approvals": 2,
                        "required_roles": ["architecture", "security"],
                        "required_teams": [
                            "architecture-platform",
                            "security-assurance",
                        ],
                    },
                    "delegations": delegations,
                }),
                encoding="utf-8",
            )
            trust_report = temp / "trust-report.json"
            verified = run(
                TOOL,
                "verify-delegated-approvals",
                review,
                "--ledger",
                ledger,
                "--trust-policy",
                trust_policy,
                "--trust-root",
                trust_root,
                "-o",
                trust_report,
            )
            self.assertTrue(json.loads(verified.stdout)["passed"])
            self.assertEqual(
                2,
                len(json.loads(trust_report.read_text(encoding="utf-8"))[
                    "active_approvals"
                ]),
            )
            catalog = temp / "catalog.json"
            trends = temp / "trends.json"
            run(TOOL, "catalog-reviews", review, "-o", catalog)
            run(
                TOOL,
                "governance-trends",
                "--snapshot",
                f"2026-07-28={review}",
                "--snapshot",
                f"2026-07-29={review}",
                "-o",
                trends,
            )
            first_log = temp / "transparency-1.json"
            second_log = temp / "transparency-2.json"
            run(TOOL, "transparency-log", catalog, "-o", first_log)
            run(
                TOOL,
                "transparency-log",
                trends,
                "--baseline",
                first_log,
                "-o",
                second_log,
            )
            transparency = json.loads(second_log.read_text(encoding="utf-8"))
            self.assertEqual(2, len(transparency["entries"]))
            self.assertEqual(1, transparency["append_only"]["added_entries"])
            verified_log = run(TOOL, "verify-transparency-log", second_log)
            self.assertTrue(json.loads(verified_log.stdout)["passed"])
            transparency["entries"][0]["document_sha256"] = "0" * 64
            second_log.write_text(json.dumps(transparency), encoding="utf-8")
            tampered = run(
                TOOL,
                "verify-transparency-log",
                second_log,
                check=False,
            )
            self.assertEqual(16, tampered.returncode)

    def test_portal_metrics_structurizr_and_adr_interoperability(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bundle = temp / "bundle"
            review = temp / "review"
            catalog = temp / "catalog.json"
            trends = temp / "trends.json"
            portal = temp / "portal"
            run(
                TOOL,
                "build",
                ASSETS / "example.architecture.json",
                "-o",
                bundle,
                "--strict",
            )
            run(
                TOOL,
                "publish",
                bundle,
                "-o",
                review,
                "--source-repository",
                "uulab/commerce",
                "--source-revision",
                "c" * 40,
                "--source-path",
                "architecture/commerce.json",
                "--strict",
            )
            run(TOOL, "catalog-reviews", review, "-o", catalog)
            run(
                TOOL,
                "catalog-portal",
                catalog,
                "-o",
                portal,
                "--title",
                "UULAB Architecture",
            )
            portal_html = (portal / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="catalog-search"', portal_html)
            self.assertIn("uulab/commerce", portal_html)
            self.assertNotRegex(
                portal_html,
                r'<(?:script|img|link)[^>]+(?:src|href)="https://',
            )
            self.assertTrue((portal / "portal.js").is_file())
            self.assertTrue((portal / "favicon.svg").is_file())
            self.assertTrue((portal / "og-image.svg").is_file())
            unsafe_catalog = temp / "unsafe-catalog.json"
            unsafe = json.loads(catalog.read_text(encoding="utf-8"))
            unsafe["reviews"][0]["source_url"] = "javascript:alert(1)"
            unsafe_catalog.write_text(json.dumps(unsafe), encoding="utf-8")
            unsafe_portal = run(
                TOOL,
                "catalog-portal",
                unsafe_catalog,
                "-o",
                temp / "unsafe-portal",
                check=False,
            )
            self.assertEqual(2, unsafe_portal.returncode)
            self.assertIn("HTTP(S)", unsafe_portal.stderr)
            run(
                TOOL,
                "governance-trends",
                "--snapshot",
                f"2026-07-28={review}",
                "--snapshot",
                f"2026-07-29={review}",
                "-o",
                trends,
            )
            prometheus = temp / "governance.prom"
            otlp = temp / "governance.otlp.json"
            metrics_report = temp / "governance-metrics.json"
            run(
                TOOL,
                "export-governance-metrics",
                trends,
                "--prometheus",
                prometheus,
                "--otlp",
                otlp,
                "--report",
                metrics_report,
            )
            self.assertIn(
                "drawio_governance_audit_score",
                prometheus.read_text(encoding="utf-8"),
            )
            otlp_metrics = json.loads(
                otlp.read_text(encoding="utf-8")
            )["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
            self.assertTrue(otlp_metrics)
            self.assertTrue(all(
                len(metric["gauge"]["dataPoints"]) == 2
                for metric in otlp_metrics
            ))
            self.assertEqual(
                "drawio-governance-metrics/v1",
                json.loads(metrics_report.read_text(encoding="utf-8"))["format"],
            )
            structurizr = temp / "workspace.json"
            structurizr.write_text(
                json.dumps({
                    "name": "Checkout",
                    "model": {
                        "people": [{"id": "1", "name": "Customer"}],
                        "softwareSystems": [{
                            "id": "2",
                            "name": "Checkout",
                            "containers": [{
                                "id": "3",
                                "name": "API",
                                "technology": "Python",
                                "components": [{
                                    "id": "4",
                                    "name": "Payment Adapter",
                                    "technology": "HTTP",
                                }],
                            }],
                        }],
                        "relationships": [{
                            "id": "5",
                            "sourceId": "1",
                            "destinationId": "3",
                            "description": "places order",
                        }, {
                            "id": "6",
                            "sourceId": "3",
                            "destinationId": "4",
                            "description": "delegates payment",
                        }],
                    },
                }),
                encoding="utf-8",
            )
            blueprint = temp / "structurizr.blueprint.json"
            exported_structurizr = temp / "round-trip.structurizr.json"
            run(TOOL, "import-structurizr", structurizr, "-o", blueprint)
            imported = json.loads(blueprint.read_text(encoding="utf-8"))
            self.assertEqual(4, len(imported["elements"]))
            self.assertEqual(2, len(imported["relations"]))
            run(
                TOOL,
                "export-structurizr",
                blueprint,
                "-o",
                exported_structurizr,
            )
            self.assertEqual(
                "drawio-structurizr-adapter/v1",
                json.loads(exported_structurizr.read_text(encoding="utf-8"))[
                    "drawioAdapter"
                ]["format"],
            )
            adrs = temp / "adrs"
            merged_blueprint = temp / "blueprint-with-adrs.json"
            run(
                TOOL,
                "export-adrs",
                ASSETS / "example.blueprint.json",
                "-o",
                adrs,
            )
            run(
                TOOL,
                "import-adrs",
                adrs,
                "--blueprint",
                ASSETS / "example.blueprint.json",
                "-o",
                merged_blueprint,
            )
            merged = json.loads(merged_blueprint.read_text(encoding="utf-8"))
            self.assertEqual(2, len(merged["decisions"]))
            self.assertEqual(
                {"event-driven-orders", "isolated-data-zone"},
                {decision["id"] for decision in merged["decisions"]},
            )

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
