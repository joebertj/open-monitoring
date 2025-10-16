#!/bin/sh
# Ultra-Minimal Geo-Monitoring Agent
# Compatible with BusyBox ash/sh, maximum compatibility

# Configuration
LOCATION="${LOCATION:-UNKNOWN}"
CENTRAL_API="http://10.27.79.2:8002"  # API port
INTERVAL=300

echo "Agent: $LOCATION started"

# Check single subdomain
check_subdomain() {
    subdomain="$1"
    start_time=$(date +%s 2>/dev/null || echo "0")

    # Try HTTPS first, fallback to HTTP
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$subdomain/" 2>/dev/null)
    response_time=$(curl -s -o /dev/null -w "%{time_total}" --max-time 10 "https://$subdomain/" 2>/dev/null | awk '{printf "%.0f", $1 * 1000}' 2>/dev/null || echo "0")

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

# Get subdomains from API (BusyBox compatible)
get_subdomains() {
    curl -s --max-time 30 "$CENTRAL_API/api/subdomains" 2>/dev/null | grep -o '"subdomain":"[^"]*"' | sed 's/.*"subdomain":"\([^"]*\)".*/\1/'
}

# Report results
report_results() {
    results="$1"
    payload="{\"results\":[$results],\"location\":\"$LOCATION\"}"

    response=$(curl -s -X POST -H "Content-Type: application/json" -d "$payload" --max-time 30 "$CENTRAL_API/api/geo-report" 2>/dev/null)
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
