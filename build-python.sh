#!/bin/bash
# Build the Python backend with PyInstaller
#
# This script builds a standalone Python executable that can be
# bundled with the Electron app.
#
# Usage:
#   ./build-python.sh           # Build for current architecture
#   ./build-python.sh clean     # Clean build artifacts
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Clean build artifacts
clean() {
    log_info "Cleaning build artifacts..."
    rm -rf build/
    rm -rf dist/
    rm -rf electron/python-dist/
    rm -rf __pycache__/
    find . -name "*.pyc" -delete
    find . -name "__pycache__" -type d -delete
    log_info "Clean complete"
}

# Build the Python backend
build() {
    log_info "Building Python backend with PyInstaller..."

    # Ensure dependencies are installed
    log_info "Installing dependencies..."
    uv sync

    # Run PyInstaller
    log_info "Running PyInstaller..."
    uv run pyinstaller trace.spec \
        --distpath electron/python-dist \
        --workpath build/pyinstaller \
        --noconfirm

    # Verify the output
    if [ -f "electron/python-dist/trace/trace" ]; then
        log_info "Build successful!"
        log_info "Output: electron/python-dist/trace/trace"

        # Show size
        SIZE=$(du -sh electron/python-dist/trace | cut -f1)
        log_info "Bundle size: $SIZE"

        # Test the executable
        log_info "Testing executable..."
        if ./electron/python-dist/trace/trace --help > /dev/null 2>&1; then
            log_info "Executable test passed!"
        else
            log_warn "Executable test failed - may require dependencies"
        fi
    else
        log_error "Build failed - executable not found"
        exit 1
    fi
}

# Main
case "${1:-build}" in
    clean)
        clean
        ;;
    build)
        build
        ;;
    rebuild)
        clean
        build
        ;;
    *)
        echo "Usage: $0 [build|clean|rebuild]"
        exit 1
        ;;
esac
