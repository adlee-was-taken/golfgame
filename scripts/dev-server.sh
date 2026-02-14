#!/bin/bash
#
# Start the Golf Game development server
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check if venv exists
if [ ! -f "bin/python" ]; then
    echo "Virtual environment not found. Run ./scripts/install.sh first."
    exit 1
fi

# Check if Docker services are running
if command -v docker &> /dev/null; then
    if ! docker ps --filter "name=redis" --format "{{.Names}}" 2>/dev/null | grep -q redis; then
        echo "Warning: Redis container not running. Start with:"
        echo "  docker-compose -f docker-compose.dev.yml up -d"
        echo ""
    fi
fi

# Load .env if exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

echo "Starting Golf Game development server..."
echo "Server will be available at http://localhost:${PORT:-8000}"
echo ""

cd server
exec ../bin/uvicorn main:app --reload --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
