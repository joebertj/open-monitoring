#!/bin/bash
# Geo-Monitoring Agent Deployment Script
# Deploys monitoring agents to remote servers without storing keys

set -e

# Configuration - HTTPS by default, fallback to HTTP
CENTRAL_API="http://10.27.79.2:8002"

# Auto-detect location based on IP or hostname
detect_location() {
    local ip=$(hostname -I | awk '{print $1}')
    local hostname=$(hostname)

    if [[ "$ip" == "192.168.15."* ]] || [[ "$hostname" == *"ph"* ]]; then
        echo "PH"
    elif [[ "$ip" == "10.27.79."* ]] || [[ "$hostname" == *"sg"* ]]; then
        echo "SG"
    else
        echo "UNKNOWN"
    fi
}

# Get agent token from central API
get_agent_token() {
    local location=$1
    # Fetch token from database via direct connection (requires DATABASE_URL on deployment machine)
    # Or get from scheduler logs during deployment
    # For now, query the API temporarily - will be replaced with DB query
    local token=$(curl -s "http://10.27.79.2:8002/api/agent-token/${location}" 2>/dev/null | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
    echo "$token"
}

# Main deployment function
deploy_to_server() {
    local server=$1
    local key_path=$2
    local location=$3

    echo "🚀 Deploying to $server ($location)..."

    # Get agent token from central server
    echo "🔐 Fetching authentication token for $location..."
    local agent_token=$(get_agent_token "$location")
    
    if [ -z "$agent_token" ]; then
        echo "❌ Failed to get agent token. Ensure scheduler is running on central server."
        return 1
    fi
    
    echo "✅ Token received: ${agent_token:0:16}..."

    # Kill any existing processes
    ssh -i "$key_path" "$server" "
        # Kill existing monitor processes and their parent shells
        pkill -f 'geo_monitor.sh' || true
        pkill -f 'geo.monitor.sh' || true
        sleep 1
    "

    # Deploy the geo_monitor.sh script from deployment directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    scp -i "$key_path" "$SCRIPT_DIR/geo_monitor.sh" "$server:~/geo_monitor.sh"
    ssh -i "$key_path" "$server" "chmod +x ~/geo_monitor.sh"

    # Start the agent with location and token
    ssh -i "$key_path" "$server" "export LOCATION=\"$location\" && export AGENT_TOKEN=\"$agent_token\" && ~/geo_monitor.sh > ~/monitor.log 2>&1 &"

    echo "✅ Deployed authenticated monitoring agent to $server"
}

# Check if required tools are available
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 required"; exit 1; }
command -v ssh >/dev/null 2>&1 || { echo "❌ ssh required"; exit 1; }

echo "🌍 BetterGovPH Geo-Monitoring Deployment"
echo "========================================"

# Check command line arguments
TARGET="${1:-all}"

if [ "$TARGET" = "sg" ] || [ "$TARGET" = "all" ]; then
    # Deploy to Singapore
    echo "📍 Deploying to Singapore..."
    deploy_to_server "joebert@10.27.79.1" "$HOME/.ssh/klti" "SG"
fi

if [ "$TARGET" = "ph" ] || [ "$TARGET" = "all" ]; then
    # Deploy to Philippines
    echo "🇵🇭 Deploying to Philippines..."
    deploy_to_server "ubnt@192.168.15.12" "$HOME/.ssh/klti" "PH"
fi

echo "🎉 Ultra-minimal geo-monitoring agents deployed!"
echo "📊 Check monitor.log on each server for agent status"
echo "🛑 To stop: ssh to server and run 'pkill -f geo_monitor.sh'"
echo "⚠️  Agents run directly without supervisor - if they crash, they stay down"
