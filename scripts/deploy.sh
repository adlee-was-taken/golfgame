#!/bin/bash
set -e

DROPLET="root@165.245.152.51"
REMOTE_DIR="/opt/golfgame"

echo "Deploying to $DROPLET..."
ssh $DROPLET "cd $REMOTE_DIR && git pull origin main && docker compose -f docker-compose.prod.yml up -d --build app"
echo "Deploy complete."
