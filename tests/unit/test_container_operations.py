#!/usr/bin/env python3
"""Unit tests for ContainerImageOperations."""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from release_manager import ContainerImageOperations, ReleaseError


class TestContainerImageOperations(unittest.TestCase):
    """Test cases for ContainerImageOperations class."""

    @patch('subprocess.run')
    def test_get_image_digest_success(self, mock_run):
        """Test get_image_digest with valid image."""
        expected_digest = 'sha256:abc123def456'
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=expected_digest,
            stderr=''
        )

        image_url = 'quay.io/test/image:latest'
        result = ContainerImageOperations.get_image_digest(image_url)

        self.assertEqual(result, expected_digest)
        mock_run.assert_called_once_with(
            ['skopeo', 'inspect', f'docker://{image_url}', '--format', '{{.Digest}}'],
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )

    @patch('subprocess.run')
    def test_get_image_digest_with_trailing_newline(self, mock_run):
        """Test get_image_digest strips whitespace."""
        expected_digest = 'sha256:abc123def456'
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=f'{expected_digest}\n',
            stderr=''
        )

        result = ContainerImageOperations.get_image_digest('quay.io/test/image:tag')

        self.assertEqual(result, expected_digest)

    @patch('subprocess.run')
    def test_get_image_digest_invalid_format(self, mock_run):
        """Test get_image_digest with invalid digest format."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='invalid-digest-format',
            stderr=''
        )

        with self.assertRaises(ReleaseError) as ctx:
            ContainerImageOperations.get_image_digest('quay.io/test/image:tag')

        self.assertIn('Invalid digest format', str(ctx.exception))

    @patch('subprocess.run')
    def test_get_image_digest_command_failed(self, mock_run):
        """Test get_image_digest when skopeo command fails."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['skopeo'],
            stderr='Error: manifest unknown'
        )

        with self.assertRaises(ReleaseError) as ctx:
            ContainerImageOperations.get_image_digest('quay.io/test/nonexistent:tag')

        self.assertIn('Failed to inspect image', str(ctx.exception))

    @patch('subprocess.run')
    def test_get_image_digest_timeout(self, mock_run):
        """Test get_image_digest with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('skopeo', 60)

        with self.assertRaises(ReleaseError) as ctx:
            ContainerImageOperations.get_image_digest('quay.io/test/image:tag')

        self.assertIn('timed out', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
