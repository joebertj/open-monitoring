#!/usr/bin/env python3
"""
Test geo-agent to verify SG location reporting works
"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def test_geo_report():
    """Send a test geo report with SG location"""
    
    # Test data with SG location
    test_data = {
        "results": [
            {
                "subdomain": "test.bettergov.ph",
                "status_code": 200,
                "response_time_ms": 150.0,
                "up": True,
                "location": "SG",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        ],
        "location": "SG"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8002/api/geo-report",
                json=test_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    print("✅ SG geo-report sent successfully")
                    result = await response.json()
                    print(f"Response: {result}")
                else:
                    print(f"❌ Failed to send geo-report: {response.status}")
                    print(await response.text())
    except Exception as e:
        print(f"❌ Error sending geo-report: {e}")

if __name__ == "__main__":
    asyncio.run(test_geo_report())
