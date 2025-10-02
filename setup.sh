#!/bin/bash
#
# Setup script for InstaSlice Release Automation
# Installs Python dependencies
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Setting up InstaSlice Release Automation..."
echo ""

# Check if PyYAML is already installed
if python3 -c "import yaml" 2>/dev/null; then
    echo "✓ PyYAML is already installed"
else
    echo "Installing PyYAML..."

    # Try different installation methods
    if pip3 install --user PyYAML 2>/dev/null; then
        echo "✓ PyYAML installed via pip3 --user"
    elif pip3 install --break-system-packages PyYAML 2>/dev/null; then
        echo "✓ PyYAML installed via pip3 --break-system-packages"
    elif brew install pyyaml 2>/dev/null; then
        echo "✓ PyYAML installed via brew"
    else
        echo "⚠ Could not install PyYAML automatically."
        echo ""
        echo "Please install manually:"
        echo "  Option 1: pip3 install --user PyYAML"
        echo "  Option 2: pip3 install --break-system-packages PyYAML"
        echo "  Option 3: brew install pyyaml"
        exit 1
    fi
fi

echo ""
echo "Making scripts executable..."
chmod +x release.sh
chmod +x src/release_manager.py

echo ""
echo "Setup complete!"
echo ""
echo "Run './release.sh --check-deps' to verify all dependencies."
