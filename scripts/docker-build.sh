#!/bin/bash
#
# Build Docker images for Golf Game
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

IMAGE_NAME="${IMAGE_NAME:-golfgame}"
TAG="${TAG:-latest}"

echo -e "${BLUE}Building Golf Game Docker image...${NC}"
echo "Image: $IMAGE_NAME:$TAG"
echo ""

docker build -t "$IMAGE_NAME:$TAG" .

echo ""
echo -e "${GREEN}Build complete!${NC}"
echo ""
echo "To run with docker-compose (production):"
echo ""
echo "  export DB_PASSWORD=your-secure-password"
echo "  export SECRET_KEY=\$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
echo "  export ACME_EMAIL=your-email@example.com"
echo "  export DOMAIN=your-domain.com"
echo "  docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "To run standalone:"
echo ""
echo "  docker run -d -p 8000:8000 \\"
echo "    -e POSTGRES_URL=postgresql://user:pass@host:5432/golf \\"
echo "    -e REDIS_URL=redis://host:6379 \\"
echo "    -e SECRET_KEY=your-secret-key \\"
echo "    $IMAGE_NAME:$TAG"
