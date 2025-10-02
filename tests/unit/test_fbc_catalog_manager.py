#!/usr/bin/env python3
"""Unit tests for FBCCatalogManager."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from release_manager import FBCCatalogManager, ReleaseError


class TestFBCCatalogManager(unittest.TestCase):
    """Test cases for FBCCatalogManager class."""

    def test_update_catalog_template_success(self):
        """Test update_catalog_template with valid template."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tf:
            template_content = """Schema: olm.semver
GenerateMajorChannels: true
GenerateMinorChannels: false
Stable:
  Bundles:
  - Image: quay.io/old/bundle@sha256:old123
"""
            tf.write(template_content)
            tf.flush()
            template_path = Path(tf.name)

        try:
            new_image = 'quay.io/new/bundle@sha256:new456'
            FBCCatalogManager.update_catalog_template(template_path, new_image)

            updated_content = template_path.read_text()
            self.assertIn(new_image, updated_content)
            self.assertNotIn('old123', updated_content)
        finally:
            template_path.unlink()

    def test_update_catalog_template_file_not_found(self):
        """Test update_catalog_template with nonexistent file."""
        template_path = Path('/nonexistent/template.yaml')
        new_image = 'quay.io/new/bundle@sha256:new456'

        with self.assertRaises(ReleaseError) as ctx:
            FBCCatalogManager.update_catalog_template(template_path, new_image)

        self.assertIn('not found', str(ctx.exception))

    def test_update_catalog_template_no_image_field(self):
        """Test update_catalog_template with template missing Image field."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as tf:
            template_content = """Schema: olm.semver
GenerateMajorChannels: true
Stable:
  Bundles: []
"""
            tf.write(template_content)
            tf.flush()
            template_path = Path(tf.name)

        try:
            new_image = 'quay.io/new/bundle@sha256:new456'

            with self.assertRaises(ReleaseError) as ctx:
                FBCCatalogManager.update_catalog_template(template_path, new_image)

            # The YAML parser will raise error about empty/invalid Bundles list
            self.assertIn('Bundles', str(ctx.exception))
        finally:
            template_path.unlink()

    @patch('subprocess.run')
    def test_regenerate_catalog_success(self, mock_run):
        """Test regenerate_catalog with successful execution."""
        catalog_json = '{"schema": "olm.bundle", "name": "test"}'
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=catalog_json,
            stderr=''
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            ocp_version = 'v4.19'

            # Create directory structure
            template_dir = repo_path / ocp_version
            template_dir.mkdir()
            template_path = template_dir / 'catalog-template.yaml'
            template_path.write_text('test: data')

            catalog_dir = template_dir / 'catalog' / 'instaslice-operator'
            catalog_dir.mkdir(parents=True)
            output_path = catalog_dir / 'catalog.json'

            FBCCatalogManager.regenerate_catalog(repo_path, ocp_version)

            # Verify output was written
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_text(), catalog_json)

            # Verify opm was called correctly
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[0], 'opm')
            self.assertEqual(call_args[1], 'alpha')
            self.assertEqual(call_args[2], 'render-template')
            self.assertEqual(call_args[3], 'semver')
            self.assertIn('--migrate-level=bundle-object-to-csv-metadata', call_args)

    @patch('subprocess.run')
    def test_regenerate_catalog_command_failed(self, mock_run):
        """Test regenerate_catalog when opm command fails."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['opm'],
            stderr='Error: invalid template'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            ocp_version = 'v4.19'

            # Create minimal structure
            template_dir = repo_path / ocp_version
            template_dir.mkdir()
            (template_dir / 'catalog-template.yaml').write_text('test: data')
            catalog_dir = template_dir / 'catalog' / 'instaslice-operator'
            catalog_dir.mkdir(parents=True)

            with self.assertRaises(ReleaseError) as ctx:
                FBCCatalogManager.regenerate_catalog(repo_path, ocp_version)

            self.assertIn('Failed to regenerate catalog', str(ctx.exception))

    @patch('subprocess.run')
    def test_regenerate_catalog_timeout(self, mock_run):
        """Test regenerate_catalog with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('opm', 60)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            ocp_version = 'v4.19'

            # Create minimal structure
            template_dir = repo_path / ocp_version
            template_dir.mkdir()
            (template_dir / 'catalog-template.yaml').write_text('test: data')
            catalog_dir = template_dir / 'catalog' / 'instaslice-operator'
            catalog_dir.mkdir(parents=True)

            with self.assertRaises(ReleaseError) as ctx:
                FBCCatalogManager.regenerate_catalog(repo_path, ocp_version)

            self.assertIn('timed out', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
