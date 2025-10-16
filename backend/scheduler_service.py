#!/usr/bin/env python3
"""
Scheduler service for automated monitoring tasks
Runs as a separate service to handle periodic uptime checks and subdomain discovery
"""

import asyncio
import os
import signal
import sys
from uptime_checker import UptimeChecker

class MonitoringScheduler:
    def __init__(self):
        self.checker = UptimeChecker()
        self.running = True

    async def start(self):
        """Start the monitoring scheduler"""
        print("🚀 Starting BetterGovPH Monitoring Scheduler")

        def signal_handler(signum, frame):
            print(f"\n⚠️  Received signal {signum}, shutting down...")
            self.running = False

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            # Start with 1-minute intervals
            await self.checker.start_scheduler(interval_minutes=1)
        except Exception as e:
            print(f"❌ Error starting scheduler: {e}")
            sys.exit(1)

    async def run_once(self):
        """Run all checks once (for testing)"""
        print("🔍 Running one-time checks...")

        try:
            # Run subdomain discovery
            await self.checker.run_discovery()

            # Run uptime checks
            await self.checker.run_checks()

            print("✅ All checks completed successfully")
        except Exception as e:
            print(f"❌ Error during checks: {e}")
            sys.exit(1)

async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='BetterGovPH Monitoring Scheduler')
    parser.add_argument('--once', action='store_true',
                       help='Run checks once and exit (for testing)')
    parser.add_argument('--interval', type=int, default=1,
                       help='Check interval in minutes (default: 1)')

    args = parser.parse_args()

    scheduler = MonitoringScheduler()

    if args.once:
        await scheduler.run_once()
    else:
        await scheduler.start()

if __name__ == "__main__":
    asyncio.run(main())
