#!/bin/bash
#
# InstaSlice Operator Release Automation
# Simple wrapper script for the Python release manager
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/src/release_manager.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is required but not installed${NC}"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

# Check Python version (require 3.8+)
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo -e "${RED}Error: Python 3.8+ required, but found ${PYTHON_VERSION}${NC}"
    exit 1
fi

# Make sure the Python script is executable
chmod +x "${PYTHON_SCRIPT}"

# Run the Python release manager with all arguments passed through
exec python3 "${PYTHON_SCRIPT}" "$@"
