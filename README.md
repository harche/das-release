# InstaSlice Operator Release Automation

Automation tool for releasing InstaSlice operator builds to OperatorHub.

## Quick Start

### Prerequisites

The tool requires the following dependencies:

- **Python 3.8+**: Runtime environment
- **PyYAML**: Python YAML parser (installed via setup.sh)
- **git**: Version control operations
- **skopeo**: Container image inspection
- **opm v1.47.0+**: OLM package manager for FBC generation

### Installation

1. Clone the repository and navigate to the release-automation directory:
```bash
cd /path/to/konflux-agent/release-automation
```

2. Run the setup script:
```bash
./setup.sh
```

This will:
- Install PyYAML Python package
- Make scripts executable

3. Check dependencies:
```bash
./release.sh --check-deps
```

If any dependencies are missing, install them:

- **Git**: https://git-scm.com/downloads
- **Skopeo**: https://github.com/containers/skopeo/blob/main/install.md
- **OPM**: https://github.com/operator-framework/operator-registry/releases
- **PyYAML**: `pip3 install --user PyYAML` or run `./setup.sh`


### Basic Usage

Run a release (with dry-run first):
```bash
# Dry run - no commits
./release.sh --dry-run

# Actual release
./release.sh
```

The tool will:
1. Get the latest operator bundle SHA from the `next` branch
2. Update the v4.19 FBC catalog template
3. Regenerate the catalog using `opm`
4. Commit the changes locally
5. Display next steps for pushing

### Advanced Usage

```bash
# Use custom repository paths
./release.sh --operator-repo /path/to/operator --fbc-repo /path/to/fbc

# Release for different OCP version
./release.sh --ocp-version v4.18

# Verbose logging
./release.sh --verbose

# Show help
./release.sh --help
```


