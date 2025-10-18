#!/bin/sh
# Ultra-Minimal Geo-Monitoring Agent
# Compatible with BusyBox ash/sh, maximum compatibility

# Configuration
LOCATION="${LOCATION:-UNKNOWN}"
CENTRAL_API="http://10.27.79.2:8002"  # API port
INTERVAL=300
TOKEN="${AGENT_TOKEN:-}"

# Validate token is provided
if [ -z "$TOKEN" ]; then
    echo "❌ ERROR: AGENT_TOKEN environment variable not set"
    echo "This agent must be deployed via deploy_geo_monitor.sh"
    exit 1
fi

echo "Agent: $LOCATION started (token: $(echo "$TOKEN" | cut -c1-16)...)"

# Check single subdomain
check_subdomain() {
    subdomain="$1"
    check_path="${2:-/}"
    start_time=$(date +%s 2>/dev/null || echo "0")

    # Try HTTPS first, fallback to HTTP
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${subdomain}${check_path}" 2>/dev/null)
    response_time=$(curl -s -o /dev/null -w "%{time_total}" --max-time 10 "https://${subdomain}${check_path}" 2>/dev/null | awk '{printf "%.0f", $1 * 1000}' 2>/dev/null || echo "0")

    if [ "$http_code" = "000" ]; then
        http_code="null"
    fi

    if [ "$http_code" -ge 200 ] 2>/dev/null && [ "$http_code" -lt 400 ] 2>/dev/null; then
        up="true"
    else
        up="false"
    fi

    echo "{\"subdomain\":\"$subdomain\",\"status_code\":$http_code,\"response_time_ms\":${response_time:-0},\"up\":$up,\"location\":\"$LOCATION\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\"}"
}

# Get subdomains with check_path from API (cross-platform compatible)
get_subdomains() {
    # Parse JSON using grep and simple sed - works on macOS, Linux, and BusyBox
    curl -s --max-time 30 "$CENTRAL_API/api/subdomains" 2>/dev/null | \
        sed 's/},{/}\n{/g' | \
        grep '"subdomain"' | \
        while IFS= read -r line; do
            # Extract subdomain
            subdomain=$(echo "$line" | sed 's/.*"subdomain":"\([^"]*\)".*/\1/')
            # Extract check_path if exists, default to /
            check_path=$(echo "$line" | grep -o '"check_path":"[^"]*"' | sed 's/"check_path":"\([^"]*\)"/\1/' || echo "/")
            [ -z "$check_path" ] && check_path="/"
            echo "$subdomain|$check_path"
        done
}

# Report results
report_results() {
    results="$1"
    payload="{\"results\":[$results],\"location\":\"$LOCATION\",\"token\":\"$TOKEN\"}"

    response=$(curl -s -X POST -H "Content-Type: application/json" -d "$payload" --max-time 30 "$CENTRAL_API/api/geo-report" 2>/dev/null)
    
    # Check if report was accepted or rejected
    if echo "$response" | grep -q '"status":"rejected"'; then
        echo "❌ Report rejected by server - token may be invalid or expired"
        exit 1
    fi
}

# Main loop
while true; do
    SUBDOMAINS=$(get_subdomains)
    if [ -n "$SUBDOMAINS" ]; then
        RESULTS=""
        echo "$SUBDOMAINS" | while IFS='|' read -r subdomain check_path; do
            if [ -n "$subdomain" ]; then
                if [ -n "$RESULTS" ]; then
                    RESULTS="$RESULTS,"
                fi
                result=$(check_subdomain "$subdomain" "${check_path:-/}")
                RESULTS="$RESULTS$result"
                
                # Report immediately to avoid losing data in subshell
                if [ -n "$result" ]; then
                    report_results "$result"
                fi
            fi
        done
    fi
    sleep "$INTERVAL"
done
