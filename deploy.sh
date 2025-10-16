#!/bin/bash
# BetterGovPH Open Monitoring Deployment Script
# Pulls latest code and restarts containers

set -e

echo "🚀 BetterGovPH Open Monitoring Deployment"
echo "========================================"

# Change to project directory
cd /home/joebert/open-monitoring

echo "📥 Pulling latest code..."
git pull

echo "🐳 Restarting containers..."
cd docker
/opt/homebrew/bin/docker-compose restart

echo "✅ Deployment complete!"
echo "🌐 Visit: https://mon.altgovph.site/"
