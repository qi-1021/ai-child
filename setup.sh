#!/bin/bash
# AI Child Setup Launcher
# Detects Python and runs the setup wizard

set -e

echo "🚀 AI Child Setup Wizard"

# Try to find Python 3
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &> /dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Python 3 not found. Please install Python 3.10 or later."
    exit 1
fi

echo "✅ Found: $PYTHON_CMD"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Run the wizard
"$PYTHON_CMD" "$SCRIPT_DIR/setup_wizard.py" "$@"
