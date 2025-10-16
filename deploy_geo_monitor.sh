#!/bin/bash
# Geo-Monitoring Agent Deployment Script
# Deploys monitoring agents to remote servers without storing keys

set -e

# Configuration - HTTPS by default, fallback to HTTP
CENTRAL_API="https://mon.altgovph.site:8443"

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
CENTRAL_API="http://10.27.79.4:8002"  # API port
INTERVAL=300

# Auto-detect location if not set
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
    start_time=$(date +%s 2>/dev/null || echo "0")

    # Try HTTPS first, fallback to HTTP
    response=$(curl -s -w "%{http_code}|%{time_total}" --max-time 10 "https://$subdomain/" 2>/dev/null)
    http_code=$(echo "$response" | cut -d'|' -f1)
    response_time=$(echo "$response" | cut -d'|' -f2 | awk '{printf "%.0f", $1 * 1000}' 2>/dev/null || echo "0")

    if [ "$http_code" = "000" ] || [ -z "$http_code" ]; then
        response=$(curl -s -w "%{http_code}|%{time_total}" --max-time 10 "http://$subdomain/" 2>/dev/null)
        http_code=$(echo "$response" | cut -d'|' -f1)
        response_time=$(echo "$response" | cut -d'|' -f2 | awk '{printf "%.0f", $1 * 1000}' 2>/dev/null || echo "0")
    fi

    up="false"
    if [ "$http_code" -ge 200 ] 2>/dev/null && [ "$http_code" -lt 400 ] 2>/dev/null; then
        up="true"
    fi

    echo "{\"subdomain\":\"$subdomain\",\"status_code\":${http_code:-null},\"response_time_ms\":${response_time:-0},\"up\":$up,\"location\":\"$LOCATION\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\"}"
}

# Get subdomains from API
get_subdomains() {
    response=$(curl -s --max-time 30 "$CENTRAL_API/api/subdomains" 2>/dev/null)
    if [ -z "$response" ]; then
        response=$(curl -s --max-time 30 "http://mon.altgovph.site:8002/api/subdomains" 2>/dev/null)
    fi
    echo "$response" | grep -o '"subdomain":"[^"]*"' | cut -d'"' -f4
}

# Report results
report_results() {
    results="$1"
    payload="{\"results\":[$results],\"location\":\"$LOCATION\"}"

    response=$(curl -s -X POST -H "Content-Type: application/json" -d "$payload" --max-time 30 "$CENTRAL_API/api/geo-report" 2>/dev/null)
    if [ -z "$response" ]; then
        curl -s -X POST -H "Content-Type: application/json" -d "$payload" --max-time 30 "http://mon.altgovph.site:8002/api/geo-report" >/dev/null 2>&1
    fi
}

# Main loop
while true; do
    SUBDOMAINS=$(get_subdomains)
    if [ -n "$SUBDOMAINS" ]; then
        RESULTS=""
        for subdomain in $SUBDOMAINS; do
            if [ -n "$RESULTS" ]; then
                RESULTS="$RESULTS,"
            fi
            result=$(check_subdomain "$subdomain")
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


# Main deployment function
deploy_to_server() {
    local server=$1
    local key_path=$2
    local location=$3

    echo "🚀 Deploying to $server ($location)..."

    # Kill any existing processes
    ssh -i "$key_path" "$server" "
        # Kill existing monitor processes
        for pid in \$(ps | grep 'geo_monitor.sh' | grep -v grep | awk '{print \$1}' 2>/dev/null || ps | grep 'geo_monitor.sh' | grep -v grep | sed 's/^ *//' | cut -d' ' -f1); do
            kill -9 \$pid 2>/dev/null || true
        done
    "

    # Generate and deploy the ultra-minimal script
    generate_monitor_script | ssh -i "$key_path" "$server" "cat > geo_monitor.sh && chmod +x geo_monitor.sh"

    # Start the agent directly with location override
    ssh -i "$key_path" "$server" "LOCATION=\"$location\" ./geo_monitor.sh > monitor.log 2>&1 &"

    echo "✅ Deployed ultra-minimal monitoring agent to $server"
}

# Check if required tools are available
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 required"; exit 1; }
command -v ssh >/dev/null 2>&1 || { echo "❌ ssh required"; exit 1; }

echo "🌍 BetterGovPH Geo-Monitoring Deployment"
echo "========================================"

# Deploy to Singapore
echo "📍 Deploying to Singapore..."
deploy_to_server "joebert@10.27.79.1" "$HOME/.ssh/klti" "SG"

# Deploy to Philippines
echo "🇵🇭 Deploying to Philippines..."
deploy_to_server "ubnt@192.168.15.12" "$HOME/.ssh/klti" "PH"

echo "🎉 Ultra-minimal geo-monitoring agents deployed!"
echo "📊 Check monitor.log on each server for agent status"
echo "🛑 To stop: ssh to server and run 'pkill -f geo_monitor.sh'"
echo "⚠️  Agents run directly without supervisor - if they crash, they stay down"
