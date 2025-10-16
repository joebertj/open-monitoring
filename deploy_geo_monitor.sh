#!/bin/bash
# Geo-Monitoring Agent Deployment Script
# Deploys monitoring agents to remote servers without storing keys

set -e

# Configuration
CENTRAL_API="http://mon.altgovph.site:8002"

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

# Generate monitoring agent script
generate_monitor_script() {
    cat << 'EOF'
#!/usr/bin/env python3
"""
Geo-distributed monitoring agent for BetterGovPH
Generated at runtime - not stored in repository
"""

import asyncio
import aiohttp
import time
import socket
import os
import sys
from datetime import datetime

class GeoMonitor:
    def __init__(self, location_name, central_api_url="http://mon.altgovph.site:8002"):
        self.location_name = location_name
        self.central_api_url = central_api_url
        self.session = None

    async def init_session(self):
        self.session = aiohttp.ClientSession()

    async def close_session(self):
        if self.session:
            await self.session.close()

    async def check_subdomain(self, subdomain):
        start_time = time.time()
        try:
            async with self.session.head(f"https://{subdomain}", timeout=aiohttp.ClientTimeout(total=10)) as response:
                response_time = (time.time() - start_time) * 1000
                return {
                    "subdomain": subdomain,
                    "status_code": response.status,
                    "response_time_ms": round(response_time, 2),
                    "up": response.status < 400,
                    "location": self.location_name,
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {
                "subdomain": subdomain,
                "status_code": None,
                "response_time_ms": round(response_time, 2),
                "up": False,
                "error": str(e),
                "location": self.location_name,
                "timestamp": datetime.utcnow().isoformat()
            }

    async def get_subdomains_from_central(self):
        try:
            async with self.session.get(f"{self.central_api_url}/api/subdomains") as response:
                if response.status == 200:
                    data = await response.json()
                    return [subdomain["subdomain"] for subdomain in data.get("subdomains", [])]
                return []
        except:
            return []

    async def report_results(self, results):
        try:
            payload = {"results": results, "location": self.location_name}
            async with self.session.post(f"{self.central_api_url}/api/geo-report", json=payload) as response:
                return response.status == 200
        except:
            return False

    async def run_monitoring_cycle(self):
        subdomains = await self.get_subdomains_from_central()
        if not subdomains:
            return

        tasks = [self.check_subdomain(subdomain) for subdomain in subdomains]
        results = await asyncio.gather(*tasks)

        success = await self.report_results(results)
        status = "✅" if success else "❌"
        up_count = sum(1 for r in results if r["up"])
        print(f"{status} {self.location_name}: {up_count}/{len(results)} up")

    async def run_continuous_monitoring(self, interval_minutes=5):
        print(f"🚀 Monitoring started from {self.location_name}")
        while True:
            try:
                await self.run_monitoring_cycle()
            except Exception as e:
                print(f"❌ Error: {e}")
            await asyncio.sleep(interval_minutes * 60)

async def main():
    # Auto-detect location
    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)

    if "ph" in hostname.lower() or ip.startswith("192.168.15."):
        location = "PH"
    elif "sg" in hostname.lower() or ip.startswith("10.27.79."):
        location = "SG"
    else:
        location = os.getenv("MONITOR_LOCATION", "UNKNOWN")

    monitor = GeoMonitor(location)
    try:
        await monitor.init_session()
        await monitor.run_continuous_monitoring()
    except KeyboardInterrupt:
        print(f"🛑 Stopped monitoring from {location}")
    finally:
        await monitor.close_session()

if __name__ == "__main__":
    asyncio.run(main())
EOF
}

# Main deployment function
deploy_to_server() {
    local server=$1
    local key_path=$2
    local location=$3

    echo "🚀 Deploying to $server ($location)..."

    # Generate and deploy the script
    generate_monitor_script | ssh -i "$key_path" "$server" "cat > geo_monitor.py && chmod +x geo_monitor.py"

    # Start the monitoring agent
    ssh -i "$key_path" "$server" "pkill -f geo_monitor.py || true"
    ssh -i "$key_path" "$server" "nohup python3 geo_monitor.py > monitor.log 2>&1 &"

    echo "✅ Deployed monitoring agent to $server"
}

# Check if required tools are available
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 required"; exit 1; }
command -v ssh >/dev/null 2>&1 || { echo "❌ ssh required"; exit 1; }

echo "🌍 BetterGovPH Geo-Monitoring Deployment"
echo "========================================"

# Deploy to Singapore
echo "📍 Deploying to Singapore..."
deploy_to_server "joebert@10.27.79.1" "~/.ssh/klti" "SG"

# Deploy to Philippines
echo "🇵🇭 Deploying to Philippines..."
deploy_to_server "ubnt@192.168.15.12" "~/.ssh/klti" "PH"

echo "🎉 Geo-monitoring agents deployed!"
echo "📊 Check monitor.log on each server for status"
echo "🛑 To stop: ssh to server and run 'pkill -f geo_monitor.py'"
