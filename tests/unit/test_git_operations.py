#!/usr/bin/env python3
"""Unit tests for GitOperations and GitHubOperations."""

import json
import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch, call, mock_open

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from release_manager import GitOperations, GitHubOperations, ReleaseError


class TestGitHubOperations(unittest.TestCase):
    """Test cases for GitHubOperations class."""

    @patch('urllib.request.urlopen')
    def test_get_latest_commit_sha_success(self, mock_urlopen):
        """Test get_latest_commit_sha with successful GitHub API response."""
        expected_sha = 'abc123def456789012345678901234567890abcd'
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'commit': {'sha': expected_sha}
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = GitHubOperations.get_latest_commit_sha('openshift', 'instaslice-operator', 'next')

        self.assertEqual(result, expected_sha)

    @patch('urllib.request.urlopen')
    def test_get_latest_commit_sha_not_found(self, mock_urlopen):
        """Test get_latest_commit_sha when branch doesn't exist."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'url', 404, 'Not Found', {}, None
        )

        with self.assertRaises(ReleaseError) as ctx:
            GitHubOperations.get_latest_commit_sha('openshift', 'instaslice-operator', 'nonexistent')

        self.assertIn('not found', str(ctx.exception))

    @patch('urllib.request.urlopen')
    def test_get_latest_commit_sha_rate_limit(self, mock_urlopen):
        """Test get_latest_commit_sha with rate limit error."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'url', 403, 'Forbidden', {}, None
        )

        with self.assertRaises(ReleaseError) as ctx:
            GitHubOperations.get_latest_commit_sha('openshift', 'instaslice-operator', 'next')

        self.assertIn('rate limit', str(ctx.exception).lower())

    @patch('urllib.request.urlopen')
    def test_get_latest_commit_sha_network_error(self, mock_urlopen):
        """Test get_latest_commit_sha with network error."""
        mock_urlopen.side_effect = urllib.error.URLError('Network error')

        with self.assertRaises(ReleaseError) as ctx:
            GitHubOperations.get_latest_commit_sha('openshift', 'instaslice-operator', 'next')

        self.assertIn('Network error', str(ctx.exception))

    @patch('urllib.request.urlopen')
    def test_get_latest_commit_sha_invalid_response(self, mock_urlopen):
        """Test get_latest_commit_sha with invalid JSON response."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"invalid": "response"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with self.assertRaises(ReleaseError) as ctx:
            GitHubOperations.get_latest_commit_sha('openshift', 'instaslice-operator', 'next')

        self.assertIn('Unexpected response', str(ctx.exception))


class TestGitOperations(unittest.TestCase):
    """Test cases for GitOperations class."""

    @patch('subprocess.run')
    def test_check_repo_clean_true(self, mock_run):
        """Test check_repo_clean when repo is clean."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr=''
        )

        result = GitOperations.check_repo_clean(Path('/fake/repo'))

        self.assertTrue(result)

    @patch('subprocess.run')
    def test_check_repo_clean_false(self, mock_run):
        """Test check_repo_clean when repo has changes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='M file.txt\n?? new_file.txt\n',
            stderr=''
        )

        result = GitOperations.check_repo_clean(Path('/fake/repo'))

        self.assertFalse(result)

    @patch('subprocess.run')
    def test_check_repo_clean_command_failed(self, mock_run):
        """Test check_repo_clean when git command fails."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=['git'],
            stderr='fatal: not a git repository'
        )

        with self.assertRaises(ReleaseError) as ctx:
            GitOperations.check_repo_clean(Path('/fake/repo'))

        self.assertIn('Failed to check git status', str(ctx.exception))

    @patch('subprocess.run')
    def test_fetch_latest_success(self, mock_run):
        """Test fetch_latest with successful execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        GitOperations.fetch_latest(Path('/fake/repo'))

        mock_run.assert_called_once_with(
            ['git', '-C', '/fake/repo', 'fetch', 'origin'],
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )

    @patch('subprocess.run')
    def test_fetch_latest_failed(self, mock_run):
        """Test fetch_latest when fetch fails."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['git'],
            stderr='fatal: unable to access'
        )

        with self.assertRaises(ReleaseError) as ctx:
            GitOperations.fetch_latest(Path('/fake/repo'))

        self.assertIn('Failed to fetch', str(ctx.exception))

    @patch('subprocess.run')
    def test_commit_changes_success(self, mock_run):
        """Test commit_changes with successful execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')

        repo_path = Path('/fake/repo')
        files = ['file1.txt', 'file2.txt']
        message = 'Test commit'

        GitOperations.commit_changes(repo_path, files, message)

        # Verify add was called
        add_call = call(
            ['git', '-C', str(repo_path), 'add', 'file1.txt', 'file2.txt'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )

        # Verify commit was called with full message
        calls = mock_run.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], add_call)

        # Check commit message includes automation footer
        commit_call = calls[1]
        # The commit command is: ['git', '-C', path, 'commit', '-m', message]
        # So message is at index 5 in the command list
        commit_cmd = commit_call[0][0]
        self.assertEqual(commit_cmd[0], 'git')
        self.assertEqual(commit_cmd[3], 'commit')
        self.assertEqual(commit_cmd[4], '-m')
        commit_message = commit_cmd[5]
        self.assertIn('Test commit', commit_message)
        self.assertIn('Generated with', commit_message)
        self.assertIn('Claude', commit_message)

    @patch('subprocess.run')
    def test_commit_changes_add_failed(self, mock_run):
        """Test commit_changes when git add fails."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['git'],
            stderr='error: pathspec did not match'
        )

        with self.assertRaises(ReleaseError) as ctx:
            GitOperations.commit_changes(
                Path('/fake/repo'),
                ['nonexistent.txt'],
                'Test'
            )

        self.assertIn('Failed to commit', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
