#!/usr/bin/env python3
"""
InstaSlice Operator Release Manager

Automates the process of releasing new InstaSlice operator builds to OperatorHub.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    # Custom colors for diff output
    RED = '\033[91m'      # For removed/old values
    GREEN = '\033[92m'    # For added/new values
    YELLOW = '\033[93m'   # For warnings/attention
    BLUE = '\033[94m'     # For info
    MAGENTA = '\033[95m'  # For headers


class DependencyError(Exception):
    """Raised when a required dependency is missing."""
    pass


class ReleaseError(Exception):
    """Raised when a release operation fails."""
    pass


@dataclass
class ReleaseConfig:
    """Configuration for the release process."""
    fbc_repo_path: Path
    operator_branch: str = "next"
    fbc_branch: str = "main"
    tenant: str = "dynamicacceleratorsl-tenant"
    bundle_component: str = "instaslice-operator-bundle-next"
    quay_registry: str = "quay.io/redhat-user-workloads"
    ocp_version: str = "v4.19"
    # GitHub repository details for API access
    operator_repo_owner: str = "openshift"
    operator_repo_name: str = "instaslice-operator"
    # FBC repository URL for cloning
    fbc_repo_url: str = "https://github.com/openshift/instaslice-fbc.git"


class DependencyChecker:
    """Checks for required system dependencies."""

    REQUIRED_TOOLS = {
        'git': 'Git version control',
        'skopeo': 'Container image inspection tool',
        'opm': 'OLM package manager (v1.47.0+)',
    }

    REQUIRED_PYTHON_PACKAGES = {
        'yaml': 'PyYAML - YAML parser',
    }

    @staticmethod
    def check_command_exists(command: str) -> bool:
        """Check if a command exists in PATH."""
        result = subprocess.run(
            ['which', command],
            capture_output=True,
            text=True
        )
        return result.returncode == 0

    @staticmethod
    def get_opm_version() -> Optional[str]:
        """Get installed opm version."""
        try:
            result = subprocess.run(
                ['opm', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Extract version from output like "Version: version.Version{OpmVersion:"v1.47.0", ...}"
                match = re.search(r'OpmVersion:"v?([0-9.]+)"', result.stdout)
                if match:
                    return match.group(1)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    @staticmethod
    def check_opm_version(min_version: str = "1.47.0") -> bool:
        """Check if opm meets minimum version requirement."""
        version = DependencyChecker.get_opm_version()
        if not version:
            return False

        # Simple version comparison (assuming semantic versioning)
        try:
            current = tuple(map(int, version.split('.')))
            required = tuple(map(int, min_version.split('.')))
            return current >= required
        except ValueError:
            return False

    @classmethod
    def check_all_dependencies(cls) -> Tuple[bool, list[str]]:
        """
        Check all required dependencies.

        Returns:
            Tuple of (all_present, missing_tools)
        """
        missing = []

        # Check command-line tools
        for tool, description in cls.REQUIRED_TOOLS.items():
            if not cls.check_command_exists(tool):
                missing.append(f"{tool} - {description}")
            elif tool == 'opm':
                if not cls.check_opm_version():
                    version = cls.get_opm_version()
                    if version:
                        missing.append(f"opm - Version {version} found, but v1.47.0+ required")
                    else:
                        missing.append(f"opm - Could not determine version, v1.47.0+ required")

        # Check Python packages
        for package, description in cls.REQUIRED_PYTHON_PACKAGES.items():
            if package == 'yaml' and yaml is None:
                missing.append(f"python3-{package} - {description}")

        return (len(missing) == 0, missing)


class GitHubOperations:
    """Handles GitHub API operations."""

    @staticmethod
    def get_latest_commit_sha(repo_owner: str, repo_name: str, branch: str) -> str:
        """
        Get the latest commit SHA from a GitHub branch via API.

        Args:
            repo_owner: GitHub repository owner (e.g., 'openshift')
            repo_name: Repository name (e.g., 'instaslice-operator')
            branch: Branch name (e.g., 'next')

        Returns:
            Commit SHA string
        """
        try:
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/branches/{branch}"
            logger.info(f"Fetching latest commit from {repo_owner}/{repo_name} branch {branch}...")

            req = urllib.request.Request(api_url)
            req.add_header('Accept', 'application/vnd.github.v3+json')

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                sha = data['commit']['sha']
                logger.info(f"Latest commit on {branch}: {sha}")
                return sha

        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ReleaseError(f"Branch '{branch}' not found in {repo_owner}/{repo_name}")
            elif e.code == 403:
                raise ReleaseError(f"GitHub API rate limit exceeded. Try again later or set GITHUB_TOKEN environment variable.")
            else:
                raise ReleaseError(f"GitHub API error: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            raise ReleaseError(f"Network error accessing GitHub API: {e.reason}")
        except KeyError:
            raise ReleaseError("Unexpected response format from GitHub API")
        except Exception as e:
            raise ReleaseError(f"Failed to get commit SHA from GitHub: {e}")


class GitOperations:
    """Handles Git repository operations."""

    @staticmethod
    def clone_repository(repo_url: str, dest_path: Path, branch: str = None) -> None:
        """
        Clone a git repository.

        Args:
            repo_url: URL of the repository to clone
            dest_path: Destination path for the clone
            branch: Optional specific branch to checkout
        """
        try:
            logger.info(f"Cloning {repo_url} to {dest_path}...")

            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = ['git', 'clone', repo_url, str(dest_path)]
            if branch:
                cmd.extend(['--branch', branch])

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5 minutes for clone
            )
            logger.info(f"Successfully cloned to {dest_path}")
        except subprocess.CalledProcessError as e:
            raise ReleaseError(f"Failed to clone repository: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise ReleaseError("Repository clone timed out (>5 minutes)")

    @staticmethod
    def check_repo_clean(repo_path: Path) -> bool:
        """Check if repository has uncommitted changes."""
        try:
            result = subprocess.run(
                ['git', '-C', str(repo_path), 'status', '--porcelain'],
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            return len(result.stdout.strip()) == 0
        except subprocess.CalledProcessError as e:
            raise ReleaseError(f"Failed to check git status: {e.stderr}")

    @staticmethod
    def fetch_latest(repo_path: Path) -> None:
        """Fetch latest changes from remote."""
        try:
            logger.info(f"Fetching latest changes from {repo_path.name}...")
            subprocess.run(
                ['git', '-C', str(repo_path), 'fetch', 'origin'],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
        except subprocess.CalledProcessError as e:
            raise ReleaseError(f"Failed to fetch: {e.stderr}")

    @staticmethod
    def commit_changes(repo_path: Path, files: list[str], message: str) -> None:
        """Commit changes to repository."""
        try:
            # Add files
            subprocess.run(
                ['git', '-C', str(repo_path), 'add'] + files,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )

            # Commit
            subprocess.run(
                ['git', '-C', str(repo_path), 'commit', '-m', message],
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            logger.info(f"Committed changes: {message}")
        except subprocess.CalledProcessError as e:
            raise ReleaseError(f"Failed to commit: {e.stderr}")


class ContainerImageOperations:
    """Handles container image operations."""

    @staticmethod
    def get_image_digest(image_url: str) -> str:
        """Get the SHA256 digest of a container image."""
        try:
            logger.info(f"Inspecting image: {image_url}")
            result = subprocess.run(
                ['skopeo', 'inspect', f'docker://{image_url}', '--format', '{{.Digest}}'],
                capture_output=True,
                text=True,
                check=True,
                timeout=60
            )
            digest = result.stdout.strip()
            if not digest.startswith('sha256:'):
                raise ReleaseError(f"Invalid digest format: {digest}")
            logger.info(f"Image digest: {digest}")
            return digest
        except subprocess.CalledProcessError as e:
            raise ReleaseError(f"Failed to inspect image: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise ReleaseError("Image inspection timed out")


class FBCCatalogManager:
    """Manages File-Based Catalog operations."""

    @staticmethod
    def preview_catalog_update(
        template_path: Path,
        new_bundle_image: str
    ) -> dict:
        """
        Preview what would be changed without modifying files.

        Returns:
            Dict with current_image, new_image, and would_change flag
        """
        try:
            logger.info(f"Previewing catalog template: {template_path}")

            if not template_path.exists():
                raise ReleaseError(f"Template not found: {template_path}")

            # Load YAML
            with template_path.open('r') as f:
                data = yaml.safe_load(f)

            # Navigate to the Image field
            if 'Stable' not in data:
                raise ReleaseError("Template missing 'Stable' section")

            if 'Bundles' not in data['Stable']:
                raise ReleaseError("Template missing 'Stable.Bundles' section")

            bundles = data['Stable']['Bundles']
            if not bundles or not isinstance(bundles, list):
                raise ReleaseError("Template has empty or invalid Bundles list")

            if 'Image' not in bundles[0]:
                raise ReleaseError("Template missing 'Image' field in first bundle")

            current_image = bundles[0]['Image']
            would_change = current_image != new_bundle_image

            if would_change:
                logger.info(f"Would update from: {current_image}")
                logger.info(f"Would update to:   {new_bundle_image}")
            else:
                logger.info(f"Catalog template already has the latest image")

            return {
                'template_path': str(template_path),
                'current_image': current_image,
                'new_image': new_bundle_image,
                'would_change': would_change
            }

        except yaml.YAMLError as e:
            raise ReleaseError(f"Failed to parse YAML template: {e}")
        except Exception as e:
            if isinstance(e, ReleaseError):
                raise
            raise ReleaseError(f"Failed to preview template: {e}")

    @staticmethod
    def update_catalog_template(
        template_path: Path,
        new_bundle_image: str
    ) -> None:
        """Update catalog template with new bundle image using YAML parsing."""
        try:
            logger.info(f"Updating catalog template: {template_path}")

            if not template_path.exists():
                raise ReleaseError(f"Template not found: {template_path}")

            # Load YAML
            with template_path.open('r') as f:
                data = yaml.safe_load(f)

            # Navigate to the Image field
            if 'Stable' not in data:
                raise ReleaseError("Template missing 'Stable' section")

            if 'Bundles' not in data['Stable']:
                raise ReleaseError("Template missing 'Stable.Bundles' section")

            bundles = data['Stable']['Bundles']
            if not bundles or not isinstance(bundles, list):
                raise ReleaseError("Template has empty or invalid Bundles list")

            if 'Image' not in bundles[0]:
                raise ReleaseError("Template missing 'Image' field in first bundle")

            current_image = bundles[0]['Image']

            # Check if image is already up to date
            if current_image == new_bundle_image:
                logger.info(f"Catalog template already has the latest image")
            else:
                logger.info(f"Updating from: {current_image}")
                logger.info(f"Updating to:   {new_bundle_image}")

            # Update the image
            bundles[0]['Image'] = new_bundle_image

            # Write back to file, preserving formatting as much as possible
            with template_path.open('w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated template with image: {new_bundle_image}")

        except yaml.YAMLError as e:
            raise ReleaseError(f"Failed to parse YAML template: {e}")
        except Exception as e:
            if isinstance(e, ReleaseError):
                raise
            raise ReleaseError(f"Failed to update template: {e}")

    @staticmethod
    def regenerate_catalog(
        fbc_repo_path: Path,
        ocp_version: str,
        opm_path: str = 'opm'
    ) -> None:
        """Regenerate FBC catalog from template."""
        try:
            template_path = fbc_repo_path / ocp_version / 'catalog-template.yaml'
            output_path = fbc_repo_path / ocp_version / 'catalog' / 'instaslice-operator' / 'catalog.json'

            logger.info(f"Regenerating catalog for {ocp_version}...")

            cmd = [
                opm_path,
                'alpha',
                'render-template',
                'semver',
                str(template_path),
                '--migrate-level=bundle-object-to-csv-metadata'
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=60
            )

            output_path.write_text(result.stdout)
            logger.info(f"Generated catalog: {output_path}")

        except subprocess.CalledProcessError as e:
            raise ReleaseError(f"Failed to regenerate catalog: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise ReleaseError("Catalog generation timed out")


class ReleaseManager:
    """Main release manager orchestrating the release process."""

    def __init__(self, config: ReleaseConfig):
        self.config = config

    def validate_and_setup_repositories(self) -> None:
        """Validate configuration and clone FBC repository if needed."""
        logger.info("Validating configuration and setting up repositories...")

        # Check FBC repository (only repo we need locally)
        if not self.config.fbc_repo_path.exists():
            logger.warning(f"FBC repository not found at {self.config.fbc_repo_path}")
            logger.info("Cloning FBC repository...")
            GitOperations.clone_repository(
                self.config.fbc_repo_url,
                self.config.fbc_repo_path
            )
        elif not (self.config.fbc_repo_path / '.git').exists():
            raise ReleaseError(f"Not a git repository: {self.config.fbc_repo_path}")

        logger.info("Configuration validated and repositories ready")

    def check_fbc_repo_clean(self) -> None:
        """Check if FBC repository is clean."""
        logger.info("Checking FBC repository status...")
        if not GitOperations.check_repo_clean(self.config.fbc_repo_path):
            raise ReleaseError(
                f"FBC repository has uncommitted changes: {self.config.fbc_repo_path}\n"
                "Please commit or stash changes before running release."
            )
        logger.info("FBC repository is clean")

    def get_latest_bundle_sha(self) -> Tuple[str, str]:
        """
        Get the latest bundle image SHA.

        Returns:
            Tuple of (commit_sha, image_digest)
        """
        logger.info("Fetching latest operator commit from GitHub...")

        # Get commit SHA via GitHub API (no clone needed!)
        commit_sha = GitHubOperations.get_latest_commit_sha(
            self.config.operator_repo_owner,
            self.config.operator_repo_name,
            self.config.operator_branch
        )

        # Build bundle image URL
        bundle_image = (
            f"{self.config.quay_registry}/"
            f"{self.config.tenant}/"
            f"{self.config.bundle_component}:{commit_sha}"
        )

        # Get image digest
        image_digest = ContainerImageOperations.get_image_digest(bundle_image)

        return commit_sha, image_digest

    def update_fbc_catalog(self, commit_sha: str, image_digest: str, dry_run: bool = False) -> dict:
        """
        Update FBC catalog with new bundle.

        Args:
            commit_sha: Operator commit SHA
            image_digest: Bundle image digest
            dry_run: If True, don't modify files, just return what would change

        Returns:
            Dict with information about changes
        """
        logger.info("Updating FBC catalog...")

        # Fetch latest from FBC repo
        GitOperations.fetch_latest(self.config.fbc_repo_path)

        # Build full bundle image reference
        bundle_image = (
            f"{self.config.quay_registry}/"
            f"{self.config.tenant}/"
            f"{self.config.bundle_component}@{image_digest}"
        )

        # Update catalog template
        template_path = (
            self.config.fbc_repo_path /
            self.config.ocp_version /
            'catalog-template.yaml'
        )

        if dry_run:
            # In dry-run mode, just check what would change without modifying files
            change_info = FBCCatalogManager.preview_catalog_update(template_path, bundle_image)
            logger.info("FBC catalog preview completed (no files modified)")
            return change_info
        else:
            FBCCatalogManager.update_catalog_template(template_path, bundle_image)

            # Regenerate catalog
            FBCCatalogManager.regenerate_catalog(
                self.config.fbc_repo_path,
                self.config.ocp_version
            )

            logger.info("FBC catalog updated successfully")
            return {
                'template_path': str(template_path),
                'new_image': bundle_image,
                'files_modified': True
            }

    def commit_fbc_changes(self, commit_sha: str) -> None:
        """Commit FBC changes."""
        logger.info("Committing FBC changes...")

        files = [
            f"{self.config.ocp_version}/catalog-template.yaml",
            f"{self.config.ocp_version}/catalog/instaslice-operator/catalog.json"
        ]

        message = (
            f"Update {self.config.ocp_version} catalog with latest instaslice operator bundle\n\n"
            f"Updates the instaslice-operator-bundle-next to commit {commit_sha} "
            f"which includes the latest merged fixes."
        )

        GitOperations.commit_changes(
            self.config.fbc_repo_path,
            files,
            message
        )

        logger.info("Changes committed successfully")

    def run_release(self, dry_run: bool = False) -> None:
        """
        Execute the complete release process.

        Args:
            dry_run: If True, don't commit changes
        """
        logger.info("=" * 60)
        logger.info("Starting InstaSlice Operator Release")
        logger.info("=" * 60)

        try:
            # Step 1: Validate configuration and setup repos
            self.validate_and_setup_repositories()

            # Step 2: Check FBC repo is clean (only if not dry-run)
            if not dry_run:
                self.check_fbc_repo_clean()

            # Step 3: Get latest bundle SHA
            commit_sha, image_digest = self.get_latest_bundle_sha()

            # Step 4: Update FBC catalog (preview in dry-run, actual update otherwise)
            change_info = self.update_fbc_catalog(commit_sha, image_digest, dry_run=dry_run)

            # Step 5: Commit changes or show preview
            if dry_run:
                # Print colored dry-run summary
                print()
                print(f"{Colors.MAGENTA}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
                print(f"{Colors.YELLOW}{Colors.BOLD}DRY RUN - No files modified{Colors.ENDC}")
                print(f"{Colors.MAGENTA}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
                print()
                print(f"{Colors.BLUE}Operator commit:{Colors.ENDC} {commit_sha}")
                print(f"{Colors.BLUE}Bundle digest:{Colors.ENDC}   {image_digest}")
                print()

                if change_info.get('would_change'):
                    print(f"{Colors.BOLD}Changes that would be made:{Colors.ENDC}")
                    print(f"  {Colors.BLUE}Template:{Colors.ENDC} {change_info.get('template_path', 'N/A')}")
                    print()

                    # Show diff-style output with colors
                    current = change_info['current_image']
                    new = change_info['new_image']

                    # Highlight the different parts
                    print(f"  {Colors.RED}{Colors.BOLD}[-] Current:{Colors.ENDC}")
                    print(f"      {Colors.RED}{current}{Colors.ENDC}")
                    print()
                    print(f"  {Colors.GREEN}{Colors.BOLD}[+] New:{Colors.ENDC}")
                    print(f"      {Colors.GREEN}{new}{Colors.ENDC}")
                    print()

                    print(f"{Colors.BOLD}Files that would be updated:{Colors.ENDC}")
                    print(f"  {Colors.YELLOW}•{Colors.ENDC} {self.config.ocp_version}/catalog-template.yaml")
                    print(f"  {Colors.YELLOW}•{Colors.ENDC} {self.config.ocp_version}/catalog/instaslice-operator/catalog.json")
                else:
                    print(f"{Colors.OKGREEN}{Colors.BOLD}✓{Colors.ENDC} No changes needed - catalog already up-to-date")

                print()
                print(f"{Colors.OKCYAN}To perform the actual release, run without --dry-run{Colors.ENDC}")
                print(f"{Colors.MAGENTA}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
                print()
            else:
                self.commit_fbc_changes(commit_sha)
                logger.info("=" * 60)
                logger.info("Release completed successfully!")
                logger.info(f"Operator commit: {commit_sha}")
                logger.info(f"Bundle digest: {image_digest}")
                logger.info("")
                logger.info("Next steps:")
                logger.info("1. Push changes: cd {} && git push".format(self.config.fbc_repo_path))
                logger.info("2. Monitor Konflux build at: https://console.redhat.com/preview/application-pipeline/workspaces")
                logger.info("3. Verify in OperatorHub once released")
                logger.info("=" * 60)

        except (DependencyError, ReleaseError) as e:
            logger.error(f"Release failed: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Release InstaSlice operator to OperatorHub',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run release with default settings
  %(prog)s

  # Run release with custom FBC repo path
  %(prog)s --fbc-repo /path/to/fbc

  # Dry run (don't commit)
  %(prog)s --dry-run

  # Specific OCP version
  %(prog)s --ocp-version v4.18
"""
    )

    parser.add_argument(
        '--fbc-repo',
        type=Path,
        help='Path to FBC repository (default: staging/instaslice-fbc)'
    )

    parser.add_argument(
        '--ocp-version',
        default='v4.19',
        help='OpenShift version (default: v4.19)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without committing changes'
    )

    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Only check dependencies and exit'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Check dependencies
    logger.info("Checking dependencies...")
    deps_ok, missing = DependencyChecker.check_all_dependencies()

    if not deps_ok:
        logger.error("Missing required dependencies:")
        for tool in missing:
            logger.error(f"  - {tool}")
        logger.error("\nInstallation instructions:")
        logger.error("  git:         https://git-scm.com/downloads")
        logger.error("  skopeo:      https://github.com/containers/skopeo/blob/main/install.md")
        logger.error("  opm:         https://github.com/operator-framework/operator-registry/releases")
        logger.error("  python3-yaml: pip3 install PyYAML")
        sys.exit(1)

    logger.info("All dependencies satisfied ✓")

    if args.check_deps:
        logger.info("Dependency check complete")
        sys.exit(0)

    # Auto-detect repository paths if not provided
    script_dir = Path(__file__).parent.parent

    # Use staging directory for FBC repository
    staging_dir = script_dir / 'staging'
    staging_dir.mkdir(exist_ok=True)

    fbc_repo = args.fbc_repo or staging_dir / 'instaslice-fbc'

    # Create configuration
    config = ReleaseConfig(
        fbc_repo_path=fbc_repo.resolve(),
        ocp_version=args.ocp_version
    )

    # Run release
    manager = ReleaseManager(config)
    manager.run_release(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
