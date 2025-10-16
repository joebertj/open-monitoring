#!/bin/bash
# Geo-Monitoring Agent - Basic Bash Script
# Compatible with minimal Linux systems, no Python dependencies

# Configuration
LOCATION="${LOCATION:-UNKNOWN}"
CENTRAL_API="${CENTRAL_API:-http://mon.altgovph.site:8002}"
INTERVAL="${INTERVAL:-300}"  # 5 minutes

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

echo "🚀 Geo-Monitoring Agent started - Location: $LOCATION"
echo "📡 Central API: $CENTRAL_API"
echo "⏰ Check interval: $INTERVAL seconds"

# Function to check a single subdomain
check_subdomain() {
    local subdomain="$1"
    local start_time=$(date +%s%N | cut -b1-13)  # milliseconds

    # Try HTTPS first, fallback to HTTP
    local response
    if command -v curl >/dev/null 2>&1; then
        # Use curl if available
        response=$(curl -s -w "%{http_code}|%{time_total}" --max-time 10 "https://$subdomain/" 2>/dev/null)
        local http_code=$(echo "$response" | cut -d'|' -f1)
        local response_time=$(echo "$response" | cut -d'|' -f2 | awk '{printf "%.0f", $1 * 1000}')

        if [ "$http_code" = "000" ]; then
            # HTTPS failed, try HTTP
            response=$(curl -s -w "%{http_code}|%{time_total}" --max-time 10 "http://$subdomain/" 2>/dev/null)
            http_code=$(echo "$response" | cut -d'|' -f1)
            response_time=$(echo "$response" | cut -d'|' -f2 | awk '{printf "%.0f", $1 * 1000}')
        fi

        local up_status="false"
        if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 400 ] 2>/dev/null; then
            up_status="true"
        fi

        cat <<EOF
{
  "subdomain": "$subdomain",
  "status_code": ${http_code:-null},
  "response_time_ms": ${response_time:-0},
  "up": $up_status,
  "location": "$LOCATION",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
}
EOF
    else
        # Fallback to basic connectivity check
        local end_time=$(date +%s%N | cut -b1-13)
        local response_time=$((end_time - start_time))

        if timeout 5 bash -c "echo >/dev/tcp/$subdomain/80" 2>/dev/null; then
            cat <<EOF
{
  "subdomain": "$subdomain",
  "status_code": 200,
  "response_time_ms": ${response_time:-0},
  "up": true,
  "location": "$LOCATION",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
}
EOF
        else
            cat <<EOF
{
  "subdomain": "$subdomain",
  "status_code": null,
  "response_time_ms": ${response_time:-0},
  "up": false,
  "location": "$LOCATION",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
}
EOF
        fi
    fi
}

# Function to get subdomains from central API
get_subdomains() {
    if command -v curl >/dev/null 2>&1; then
        curl -s --max-time 30 "$CENTRAL_API/api/subdomains" 2>/dev/null | \
        grep -o '"subdomain":"[^"]*"' | cut -d'"' -f4
    else
        echo ""
    fi
}

# Function to report results to central API
report_results() {
    local results="$1"

    if command -v curl >/dev/null 2>&1; then
        local payload="{\"results\":[$results], \"location\":\"$LOCATION\"}"
        curl -s -X POST \
             -H "Content-Type: application/json" \
             -d "$payload" \
             --max-time 30 \
             "$CENTRAL_API/api/geo-report" >/dev/null 2>&1
    fi
}

# Main monitoring loop
while true; do
    echo "$(date): Starting monitoring cycle..."

    # Get subdomains to monitor
    SUBDOMAINS=$(get_subdomains)

    if [ -n "$SUBDOMAINS" ]; then
        echo "Monitoring $(echo "$SUBDOMAINS" | wc -l) subdomains"

        # Check each subdomain
        RESULTS=""
        for subdomain in $SUBDOMAINS; do
            if [ -n "$RESULTS" ]; then
                RESULTS="$RESULTS,"
            fi
            result=$(check_subdomain "$subdomain")
            RESULTS="$RESULTS$result"
        done

        # Report results
        if [ -n "$RESULTS" ]; then
            report_results "$RESULTS"
            echo "✅ Reported results to central API"
        fi
    else
        echo "❌ No subdomains to monitor"
    fi

    echo "💤 Sleeping for $INTERVAL seconds..."
    sleep "$INTERVAL"
done
