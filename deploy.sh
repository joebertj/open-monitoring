#!/bin/bash
# BetterGovPH Open Monitoring Deployment Script
# Pulls latest code and restarts containers

set -e

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_COMPOSE_CMD="/opt/homebrew/bin/docker-compose"
DOMAIN="mon.altgovph.site"

echo "🚀 BetterGovPH Open Monitoring Deployment"
echo "========================================"

# Change to project directory
cd "$PROJECT_DIR"

# Check git status
echo "🔍 Checking git status..."
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Local changes detected. Stashing..."
    git stash
fi

# Pull latest code
echo "📥 Pulling latest code..."
GIT_OUTPUT=$(git pull 2>&1)
if echo "$GIT_OUTPUT" | grep -q "Already up to date"; then
    echo "✅ Already up to date"
else
    echo "✅ Code updated: $GIT_OUTPUT"
fi

# Check if docker-compose exists
if [ ! -x "$DOCKER_COMPOSE_CMD" ]; then
    echo "❌ Docker Compose not found at $DOCKER_COMPOSE_CMD"
    echo "🔍 Searching for docker-compose..."
    DOCKER_COMPOSE_CMD=$(which docker-compose 2>/dev/null || echo "")
    if [ -z "$DOCKER_COMPOSE_CMD" ]; then
        echo "❌ docker-compose not found in PATH"
        exit 1
    fi
fi

# Change to docker directory
cd docker

# Check if containers are running
echo "🐳 Checking container status..."
if ! $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
    echo "⚠️  Containers not running. Starting..."
    $DOCKER_COMPOSE_CMD up -d
else
    echo "🔄 Restarting containers..."
    $DOCKER_COMPOSE_CMD restart
fi

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 5

# Health check
echo "🏥 Running health checks..."
HEALTH_URL="https://$DOMAIN/api/health"
if curl -s --max-time 10 "$HEALTH_URL" > /dev/null; then
    echo "✅ API health check passed"
else
    echo "⚠️  API health check failed, but continuing..."
fi

# Check dashboard
DASHBOARD_URL="https://$DOMAIN/"
if curl -s --max-time 10 "$DASHBOARD_URL" | grep -q "BetterGovPH"; then
    echo "✅ Dashboard check passed"
else
    echo "⚠️  Dashboard check failed, but continuing..."
fi

echo "✅ Deployment complete!"
echo "🌐 Dashboard: https://$DOMAIN/"
echo "🔗 API: https://$DOMAIN/api/"
echo "📊 Check status: https://$DOMAIN/api/health"
