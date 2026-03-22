#!/bin/bash
# Test script to verify Ollama model registration

set -e

echo "🧪 Testing Ollama Model Registration"
echo "===================================="
echo ""

# Check Ollama is running
echo "Step 1: Checking Ollama connection..."
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not installed. Please install from https://ollama.com"
    exit 1
fi

# Try to connect
if timeout 2 curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running"
else
    echo "❌ Cannot connect to Ollama at http://localhost:11434"
    echo "   Start Ollama with: ollama serve"
    exit 1
fi

echo ""
echo "Step 2: Listing available models..."
echo ""
ollama list || echo "No models yet"

echo ""
echo "Step 3: Checking for local GGUF files..."
MODELS_DIR="/Volumes/mac第二磁盘/ollama/models"

if [ ! -d "$MODELS_DIR" ]; then
    echo "❌ Models directory not found: $MODELS_DIR"
    exit 1
fi

echo "📂 Found models directory: $MODELS_DIR"
echo ""

# Count GGUF files
GGUF_COUNT=$(find "$MODELS_DIR" -name "*.gguf" 2>/dev/null | wc -l)
echo "📦 Found $GGUF_COUNT GGUF files:"
find "$MODELS_DIR" -name "*.gguf" 2>/dev/null | while read file; do
    SIZE=$(ls -lh "$file" | awk '{print $5}')
    echo "   • $file ($SIZE)"
done

echo ""
echo "✅ All checks passed! Models are ready for registration."
echo ""
echo "💡 Run the setup wizard to automatically register these models:"
echo "   python3 setup_wizard.py"
