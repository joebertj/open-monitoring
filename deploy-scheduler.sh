#!/bin/bash
# BetterGovPH Monitoring Scheduler Deployment Script
# This script sets up the monitoring scheduler as a systemd service

set -e

echo "🚀 Deploying BetterGovPH Monitoring Scheduler"

# Check if running as root or with sudo
if [[ $EUID -eq 0 ]]; then
    echo "❌ This script should not be run as root. Run as the application user."
    exit 1
fi

# Get the absolute path of the project
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="monitoring-scheduler"
SERVICE_FILE="$PROJECT_DIR/systemd/$SERVICE_NAME.service"
SOCKET_FILE="$PROJECT_DIR/systemd/$SERVICE_NAME.socket"

echo "📁 Project directory: $PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv "$PROJECT_DIR/venv"
fi

# Activate virtual environment and install dependencies
echo "📦 Installing Python dependencies..."
source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/backend/requirements.txt"

# Test the scheduler
echo "🧪 Testing scheduler..."
python "$PROJECT_DIR/backend/scheduler_service.py" --once

if [ $? -ne 0 ]; then
    echo "❌ Scheduler test failed!"
    exit 1
fi

echo "✅ Scheduler test passed!"

# Create systemd service directory if it doesn't exist
sudo mkdir -p /etc/systemd/system

# Copy service files
echo "📋 Installing systemd service..."
sudo cp "$SERVICE_FILE" /etc/systemd/system/
sudo cp "$SOCKET_FILE" /etc/systemd/system/

# Update service file with correct paths
sudo sed -i "s|/home/joebert/open-monitoring|$PROJECT_DIR|g" "/etc/systemd/system/$SERVICE_NAME.service"
sudo sed -i "s|joebert|$USER|g" "/etc/systemd/system/$SERVICE_NAME.service"

# Reload systemd and enable service
echo "🔄 Reloading systemd..."
sudo systemctl daemon-reload

echo "🎯 Enabling and starting service..."
sudo systemctl enable "$SERVICE_NAME.socket"
sudo systemctl enable "$SERVICE_NAME.service"
sudo systemctl start "$SERVICE_NAME.service"

# Wait a moment and check status
sleep 3
echo "📊 Service status:"
sudo systemctl status "$SERVICE_NAME.service" --no-pager -l

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Management commands:"
echo "  Start:   sudo systemctl start $SERVICE_NAME"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Restart: sudo systemctl restart $SERVICE_NAME"
echo "  Status:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "🔍 Health check: curl http://localhost:8002/api/health"
echo "🎛️  Control panel: http://localhost:3001/subdomains"
