#!/usr/bin/env python3
"""
End-to-end tests for release automation.

These tests interact with real repositories and container registries.
They should be run in a safe test environment.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from release_manager import (
    ReleaseConfig,
    ReleaseManager,
    DependencyChecker,
    GitHubOperations,
    ContainerImageOperations,
)


class TestE2ERelease(unittest.TestCase):
    """End-to-end test cases for full release workflow."""

    @classmethod
    def setUpClass(cls):
        """Check dependencies before running E2E tests."""
        deps_ok, missing = DependencyChecker.check_all_dependencies()
        if not deps_ok:
            raise unittest.SkipTest(
                f"Required dependencies missing: {', '.join(missing)}\n"
                "Install them to run E2E tests."
            )

    def setUp(self):
        """Set up test environment."""
        # Get FBC repository path from environment or use default
        self.fbc_repo = os.getenv(
            'FBC_REPO_PATH',
            str(Path.home() / 'repos' / 'konflux-agent' / 'release-automation' / 'staging' / 'instaslice-fbc')
        )

        # Skip if FBC repo doesn't exist
        if not Path(self.fbc_repo).exists():
            self.skipTest(f"FBC repo not found: {self.fbc_repo}")

    def test_dependency_check(self):
        """Test that all dependencies are available."""
        deps_ok, missing = DependencyChecker.check_all_dependencies()
        self.assertTrue(deps_ok, f"Missing dependencies: {missing}")

    def test_get_real_commit_sha_from_github(self):
        """Test getting real commit SHA from GitHub API."""
        # Get commit SHA via API
        sha = GitHubOperations.get_latest_commit_sha('openshift', 'instaslice-operator', 'next')

        # Verify it's a valid SHA (40 hex characters)
        self.assertEqual(len(sha), 40)
        self.assertTrue(all(c in '0123456789abcdef' for c in sha.lower()))

    def test_inspect_real_bundle_image(self):
        """Test inspecting a real bundle image from quay.io."""
        # First get a real commit SHA from GitHub API
        commit_sha = GitHubOperations.get_latest_commit_sha('openshift', 'instaslice-operator', 'next')

        # Build image URL
        image_url = (
            f"quay.io/redhat-user-workloads/"
            f"dynamicacceleratorsl-tenant/"
            f"instaslice-operator-bundle-next:{commit_sha}"
        )

        # Get digest - this tests actual network connectivity and auth
        try:
            digest = ContainerImageOperations.get_image_digest(image_url)

            # Verify digest format
            self.assertTrue(digest.startswith('sha256:'))
            self.assertEqual(len(digest), 71)  # 'sha256:' + 64 hex chars
        except Exception as e:
            # If image doesn't exist for this commit, that's okay for the test
            # We're mainly testing that skopeo works
            if 'manifest unknown' in str(e).lower():
                self.skipTest(f"Bundle image not yet built for commit {commit_sha}")
            else:
                raise

    def test_fbc_catalog_template_exists(self):
        """Test that FBC catalog template exists and is readable."""
        template_path = Path(self.fbc_repo) / 'v4.19' / 'catalog-template.yaml'

        self.assertTrue(template_path.exists(), "Catalog template not found")
        self.assertTrue(template_path.is_file(), "Catalog template is not a file")

        # Read and verify basic structure
        content = template_path.read_text()
        self.assertIn('Schema:', content)
        self.assertIn('Bundles:', content)
        self.assertIn('Image:', content)

    def test_dry_run_release(self):
        """Test full release workflow in dry-run mode (no commits)."""
        config = ReleaseConfig(
            fbc_repo_path=Path(self.fbc_repo),
            ocp_version='v4.19'
        )

        manager = ReleaseManager(config)

        # This should complete without errors
        try:
            # Save original FBC state
            template_path = config.fbc_repo_path / 'v4.19' / 'catalog-template.yaml'
            catalog_path = config.fbc_repo_path / 'v4.19' / 'catalog' / 'instaslice-operator' / 'catalog.json'

            original_template = template_path.read_text()
            original_catalog = catalog_path.read_text()

            # Run dry run
            manager.run_release(dry_run=True)

            # Verify files were modified (but not committed)
            new_template = template_path.read_text()
            new_catalog = catalog_path.read_text()

            # Files should have changed
            # (unless by coincidence we're releasing the same version)
            # We mainly verify no exceptions were raised

            # Restore original state
            template_path.write_text(original_template)
            catalog_path.write_text(original_catalog)

        except Exception as e:
            self.fail(f"Dry run release failed: {e}")

    def test_validate_real_config(self):
        """Test configuration validation with real paths."""
        config = ReleaseConfig(
            fbc_repo_path=Path(self.fbc_repo),
        )

        manager = ReleaseManager(config)

        # This should not raise
        try:
            manager.validate_and_setup_repositories()
        except Exception as e:
            self.fail(f"Configuration validation failed: {e}")

    def test_opm_render_real_template(self):
        """Test running opm against real catalog template."""
        fbc_path = Path(self.fbc_repo)
        template_path = fbc_path / 'v4.19' / 'catalog-template.yaml'

        if not template_path.exists():
            self.skipTest("Catalog template not found")

        # Run opm to validate template is correct
        try:
            result = subprocess.run(
                [
                    'opm',
                    'alpha',
                    'render-template',
                    'semver',
                    str(template_path),
                    '--migrate-level=bundle-object-to-csv-metadata'
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=60
            )

            # Verify output is valid JSON
            import json
            catalog_data = json.loads(result.stdout)

            # Basic validation
            self.assertIsInstance(catalog_data, dict)
            self.assertIn('schema', catalog_data)

        except subprocess.CalledProcessError as e:
            self.fail(f"opm failed: {e.stderr}")
        except json.JSONDecodeError as e:
            self.fail(f"opm output is not valid JSON: {e}")


class TestE2EIntegrationChecks(unittest.TestCase):
    """Integration checks that verify external dependencies."""

    def test_quay_registry_accessible(self):
        """Test that quay.io registry is accessible."""
        # Try to inspect a known public image
        test_image = "quay.io/prometheus/prometheus:latest"

        try:
            result = subprocess.run(
                ['skopeo', 'inspect', f'docker://{test_image}'],
                capture_output=True,
                text=True,
                timeout=30
            )

            # If we can access quay.io, returncode should be 0
            self.assertEqual(result.returncode, 0, "Cannot access quay.io registry")

        except subprocess.TimeoutExpired:
            self.fail("Timeout accessing quay.io - network issues?")
        except FileNotFoundError:
            self.skipTest("skopeo not installed")

    def test_github_accessible(self):
        """Test that github.com is accessible for git operations."""
        # Try to fetch from a public repo
        try:
            result = subprocess.run(
                ['git', 'ls-remote', 'https://github.com/konflux-ci/docs.git', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=30
            )

            self.assertEqual(result.returncode, 0, "Cannot access github.com")
            self.assertTrue(len(result.stdout) > 0, "No output from git ls-remote")

        except subprocess.TimeoutExpired:
            self.fail("Timeout accessing github.com - network issues?")
        except FileNotFoundError:
            self.skipTest("git not installed")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
