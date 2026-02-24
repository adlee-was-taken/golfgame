#!/bin/bash
set -e

DROPLET="root@129.212.150.189"
REMOTE_DIR="/opt/golfgame"

echo "Syncing to staging ($DROPLET)..."
rsync -az --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='node_modules' \
    --exclude='.env' \
    --exclude='internal/' \
    server/ "$DROPLET:$REMOTE_DIR/server/"
rsync -az --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='node_modules' \
    client/ "$DROPLET:$REMOTE_DIR/client/"

echo "Rebuilding app container..."
ssh $DROPLET "cd $REMOTE_DIR && docker compose -f docker-compose.staging.yml up -d --build app"
echo "Staging deploy complete."
