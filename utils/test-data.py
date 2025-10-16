#!/usr/bin/env python3
"""
Test script to populate the monitoring database with sample data
Run this after starting the Docker containers
"""

import asyncio
import asyncpg
import json
import random
from datetime import datetime, timedelta

async def insert_sample_data():
    """Insert sample monitoring data for testing"""

    # Connect to database
    conn = await asyncpg.connect(
        user='monitor',
        password='monitor123',
        database='monitoring',
        host='localhost',
        port=5433
    )

    print("Connected to database")

    # Sample hosts and services
    hosts = ['web-server-01', 'web-server-02', 'db-server-01', 'cache-server-01']
    services = ['nginx', 'postgresql', 'redis', 'system']

    # Generate sample metrics for the last 24 hours
    base_time = datetime.utcnow() - timedelta(hours=24)

    print("Inserting sample metrics...")

    for hour in range(24):
        for minute in range(0, 60, 5):  # Every 5 minutes
            timestamp = base_time + timedelta(hours=hour, minutes=minute)

            for host in hosts:
                for service in services:
                    # CPU usage
                    cpu_value = random.uniform(10, 90)
                    cpu_status = 'ok' if cpu_value < 80 else 'warning' if cpu_value < 90 else 'critical'

                    await conn.execute("""
                        INSERT INTO monitoring.metrics (time, host, service, metric_name, value, status, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, timestamp, host, service, 'cpu_usage_percent',
                       cpu_value, cpu_status, json.dumps({'cores': 4}))

                    # Memory usage
                    mem_value = random.uniform(20, 95)
                    mem_status = 'ok' if mem_value < 85 else 'warning' if mem_value < 95 else 'critical'

                    await conn.execute("""
                        INSERT INTO monitoring.metrics (time, host, service, metric_name, value, status, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, timestamp, host, service, 'memory_usage_percent',
                       mem_value, mem_status, json.dumps({'total_gb': 16}))

                    # Response time (for web services)
                    if service in ['nginx']:
                        response_time = random.uniform(50, 500)
                        response_status = 'ok' if response_time < 300 else 'warning' if response_time < 400 else 'critical'

                        await conn.execute("""
                            INSERT INTO monitoring.metrics (time, host, service, metric_name, value, status, metadata)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """, timestamp, host, service, 'response_time_ms',
                           response_time, response_status, json.dumps({'endpoint': '/api/health'}))

    # Insert some sample alerts
    print("Inserting sample alerts...")

    alerts = [
        {
            'host': 'web-server-01',
            'service': 'nginx',
            'severity': 'critical',
            'message': 'High CPU usage detected: 95%'
        },
        {
            'host': 'db-server-01',
            'service': 'postgresql',
            'severity': 'warning',
            'message': 'Slow query performance detected'
        },
        {
            'host': 'cache-server-01',
            'service': 'redis',
            'severity': 'info',
            'message': 'Memory usage above 80%'
        }
    ]

    for alert in alerts:
        await conn.execute("""
            INSERT INTO monitoring.alerts (time, host, service, severity, message)
            VALUES ($1, $2, $3, $4, $5)
        """, datetime.utcnow() - timedelta(minutes=random.randint(5, 120)),
           alert['host'], alert['service'], alert['severity'], alert['message'])

    await conn.close()
    print("Sample data inserted successfully!")
    print("\nYou can now visit http://localhost:3001 to see the dashboard")

if __name__ == "__main__":
    asyncio.run(insert_sample_data())
