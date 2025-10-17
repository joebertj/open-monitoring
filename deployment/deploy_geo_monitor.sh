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

# Generate ultra-minimal monitoring agent script (sh-compatible)
    generate_monitor_script() {
        cat << 'EOF'
#!/bin/sh
# Ultra-Minimal Geo-Monitoring Agent
# Compatible with BusyBox ash/sh, maximum compatibility

# Configuration
LOCATION="${LOCATION:-UNKNOWN}"
CENTRAL_API="http://10.27.79.2:8002"  # API port
INTERVAL=300

# Auto-detect location if not explicitly set
if [ "$LOCATION" = "UNKNOWN" ]; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}' 2>/dev/null || echo "unknown")
    HOSTNAME=$(hostname 2>/dev/null || echo "unknown")

    if echo "$IP" | grep -q "192\.168\.15\." || echo "$HOSTNAME" | grep -qi "ph"; then
        LOCATION="PH"
    elif echo "$IP" | grep -q "10\.27\.79\." || echo "$HOSTNAME" | grep -qi "sg"; then
        LOCATION="SG"
    else
        LOCATION="EU"
    fi
fi

echo "Agent: $LOCATION started"

# Check single subdomain
check_subdomain() {
    subdomain="$1"
    check_path="${2:-/}"
    start_time=$(date +%s 2>/dev/null || echo "0")

    # Try HTTPS first, fallback to HTTP
    response=$(curl -s -w "%{http_code}|%{time_total}" --max-time 10 "https://${subdomain}${check_path}" 2>/dev/null)
    http_code=$(echo "$response" | cut -d'|' -f1)
    response_time=$(echo "$response" | cut -d'|' -f2 | awk '{printf "%.0f", $1 * 1000}' 2>/dev/null || echo "0")

    if [ "$http_code" = "000" ] || [ -z "$http_code" ]; then
        response=$(curl -s -w "%{http_code}|%{time_total}" --max-time 10 "http://${subdomain}${check_path}" 2>/dev/null)
        http_code=$(echo "$response" | cut -d'|' -f1)
        response_time=$(echo "$response" | cut -d'|' -f2 | awk '{printf "%.0f", $1 * 1000}' 2>/dev/null || echo "0")
    fi

    up="false"
    if [ "$http_code" -ge 200 ] 2>/dev/null && [ "$http_code" -lt 400 ] 2>/dev/null; then
        up="true"
    fi

    echo "{\"subdomain\":\"$subdomain\",\"status_code\":${http_code:-null},\"response_time_ms\":${response_time:-0},\"up\":$up,\"location\":\"$LOCATION\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\"}"
}

# Get subdomains from API (returns JSON with subdomain and check_path)
get_subdomains() {
    response=$(curl -s --max-time 30 "$CENTRAL_API/api/subdomains" 2>/dev/null)
    if [ -z "$response" ]; then
        response=$(curl -s --max-time 30 "http://10.27.79.2:8002/api/subdomains" 2>/dev/null)
    fi
    echo "$response"
}

# Report results
report_results() {
    results="$1"
    payload="{\"results\":[$results],\"location\":\"$LOCATION\"}"

    response=$(curl -s -X POST -H "Content-Type: application/json" -d "$payload" --max-time 30 "$CENTRAL_API/api/geo-report" 2>/dev/null)
        if [ -z "$response" ]; then
            curl -s -X POST -H "Content-Type: application/json" -d "$payload" --max-time 30 "http://10.27.79.2:8002/api/geo-report" >/dev/null 2>&1
        fi
}

# Main loop
while true; do
    SUBDOMAIN_DATA=$(get_subdomains)
    if [ -n "$SUBDOMAIN_DATA" ]; then
        # Parse JSON to extract subdomain and check_path pairs
        # Use grep and sed to extract each subdomain entry with its check_path
        SUBDOMAINS=$(echo "$SUBDOMAIN_DATA" | grep -o '"subdomain":"[^"]*"' | cut -d'"' -f4)
        
        RESULTS=""
        for subdomain in $SUBDOMAINS; do
            # Extract check_path for this specific subdomain from the JSON
            check_path=$(echo "$SUBDOMAIN_DATA" | grep -A1 "\"subdomain\":\"$subdomain\"" | grep '"check_path"' | cut -d'"' -f4)
            # Default to / if check_path is empty
            check_path="${check_path:-/}"
            
            if [ -n "$RESULTS" ]; then
                RESULTS="$RESULTS,"
            fi
            result=$(check_subdomain "$subdomain" "$check_path")
            RESULTS="$RESULTS$result"
        done
        if [ -n "$RESULTS" ]; then
            report_results "$RESULTS"
        fi
    fi
    sleep "$INTERVAL"
done
EOF
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

    # Generate and deploy the ultra-minimal script
    generate_monitor_script | ssh -i "$key_path" "$server" "cat > geo_monitor.sh && chmod +x geo_monitor.sh"

    # Start the agent with location and token
    ssh -i "$key_path" "$server" "export LOCATION=\"$location\" && export AGENT_TOKEN=\"$agent_token\" && ./geo_monitor.sh > monitor.log 2>&1 &"

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
