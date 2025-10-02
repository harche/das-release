#!/usr/bin/env python3
"""Unit tests for DependencyChecker."""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from release_manager import DependencyChecker


class TestDependencyChecker(unittest.TestCase):
    """Test cases for DependencyChecker class."""

    @patch('subprocess.run')
    def test_check_command_exists_found(self, mock_run):
        """Test check_command_exists when command is found."""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        result = DependencyChecker.check_command_exists('git')

        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ['which', 'git'],
            capture_output=True,
            text=True
        )

    @patch('subprocess.run')
    def test_check_command_exists_not_found(self, mock_run):
        """Test check_command_exists when command is not found."""
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')

        result = DependencyChecker.check_command_exists('nonexistent')

        self.assertFalse(result)

    @patch('subprocess.run')
    def test_get_opm_version_success(self, mock_run):
        """Test get_opm_version with valid output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='Version: version.Version{OpmVersion:"v1.47.0", GitCommit:"abc123", BuildDate:"2024-01-01"}',
            stderr=''
        )

        version = DependencyChecker.get_opm_version()

        self.assertEqual(version, "1.47.0")

    @patch('subprocess.run')
    def test_get_opm_version_no_v_prefix(self, mock_run):
        """Test get_opm_version with version without 'v' prefix."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='Version: version.Version{OpmVersion:"1.48.0", GitCommit:"def456"}',
            stderr=''
        )

        version = DependencyChecker.get_opm_version()

        self.assertEqual(version, "1.48.0")

    @patch('subprocess.run')
    def test_get_opm_version_command_not_found(self, mock_run):
        """Test get_opm_version when opm is not installed."""
        mock_run.side_effect = FileNotFoundError()

        version = DependencyChecker.get_opm_version()

        self.assertIsNone(version)

    @patch('subprocess.run')
    def test_get_opm_version_timeout(self, mock_run):
        """Test get_opm_version with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('opm', 5)

        version = DependencyChecker.get_opm_version()

        self.assertIsNone(version)

    def test_check_opm_version_meets_requirement(self):
        """Test check_opm_version when version meets requirement."""
        with patch.object(DependencyChecker, 'get_opm_version', return_value='1.47.0'):
            result = DependencyChecker.check_opm_version('1.47.0')
            self.assertTrue(result)

    def test_check_opm_version_exceeds_requirement(self):
        """Test check_opm_version when version exceeds requirement."""
        with patch.object(DependencyChecker, 'get_opm_version', return_value='1.50.5'):
            result = DependencyChecker.check_opm_version('1.47.0')
            self.assertTrue(result)

    def test_check_opm_version_below_requirement(self):
        """Test check_opm_version when version is below requirement."""
        with patch.object(DependencyChecker, 'get_opm_version', return_value='1.46.0'):
            result = DependencyChecker.check_opm_version('1.47.0')
            self.assertFalse(result)

    def test_check_opm_version_not_installed(self):
        """Test check_opm_version when opm is not installed."""
        with patch.object(DependencyChecker, 'get_opm_version', return_value=None):
            result = DependencyChecker.check_opm_version('1.47.0')
            self.assertFalse(result)

    @patch.object(DependencyChecker, 'check_command_exists')
    @patch.object(DependencyChecker, 'check_opm_version')
    def test_check_all_dependencies_all_present(self, mock_opm_version, mock_command_exists):
        """Test check_all_dependencies when all tools are present."""
        mock_command_exists.return_value = True
        mock_opm_version.return_value = True

        all_ok, missing = DependencyChecker.check_all_dependencies()

        self.assertTrue(all_ok)
        self.assertEqual(len(missing), 0)

    @patch.object(DependencyChecker, 'check_command_exists')
    def test_check_all_dependencies_missing_git(self, mock_command_exists):
        """Test check_all_dependencies when git is missing."""
        def side_effect(tool):
            return tool != 'git'

        mock_command_exists.side_effect = side_effect

        all_ok, missing = DependencyChecker.check_all_dependencies()

        self.assertFalse(all_ok)
        self.assertTrue(any('git' in m for m in missing))

    @patch.object(DependencyChecker, 'check_command_exists')
    @patch.object(DependencyChecker, 'check_opm_version')
    def test_check_all_dependencies_old_opm(self, mock_opm_version, mock_command_exists):
        """Test check_all_dependencies when opm version is too old."""
        mock_command_exists.return_value = True
        mock_opm_version.return_value = False

        with patch.object(DependencyChecker, 'get_opm_version', return_value='1.40.0'):
            all_ok, missing = DependencyChecker.check_all_dependencies()

            self.assertFalse(all_ok)
            self.assertTrue(any('opm' in m and '1.40.0' in m for m in missing))


if __name__ == '__main__':
    unittest.main()
