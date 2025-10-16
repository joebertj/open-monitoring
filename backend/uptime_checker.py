#!/usr/bin/env python3
"""
Uptime checker for bettergov.ph subdomains
Runs every minute to check subdomain availability and detect platforms
"""

import asyncio
import aiohttp
import asyncpg
import time
import json
from datetime import datetime
import os
import re
from urllib.parse import urlparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

class PlatformDetector:
    """Detect web server platforms based on HTTP headers and responses"""

    @staticmethod
    def detect_platform(headers, response_text=""):
        """Detect platform from HTTP headers and response content"""
        headers = {k.lower(): v for k, v in headers.items()}

        # Cloudflare detection
        if 'cf-ray' in headers or 'cf-cache-status' in headers or 'cf-request-id' in headers:
            return 'Cloudflare'

        # Server header analysis with version detection
        server = headers.get('server', '').lower()
        raw_server = headers.get('server', '')

        if 'nginx' in server:
            version_match = re.search(r'nginx/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Nginx{version}'
        elif 'apache' in server:
            version_match = re.search(r'apache/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Apache{version}'
        elif 'iis' in server or 'microsoft-iis' in server:
            version_match = re.search(r'microsoft-iis/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'IIS{version}'
        elif 'lighttpd' in server:
            version_match = re.search(r'lighttpd/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Lighttpd{version}'
        elif 'caddy' in server:
            version_match = re.search(r'caddy/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Caddy{version}'
        elif 'node.js' in server or 'express' in server:
            return 'Node.js'
        elif 'gunicorn' in server:
            version_match = re.search(r'gunicorn/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Gunicorn{version}'
        elif 'uwsgi' in server:
            return 'uWSGI'
        elif 'uvicorn' in server:
            version_match = re.search(r'uvicorn/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Uvicorn{version}'
        elif 'hypercorn' in server:
            return 'Hypercorn'
        elif 'daphne' in server:
            return 'Daphne'
        elif 'tomcat' in server:
            version_match = re.search(r'tomcat/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Tomcat{version}'
        elif 'jetty' in server:
            version_match = re.search(r'jetty/([\d.]+)', raw_server)
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Jetty{version}'

        # X-Powered-By header with version detection
        powered_by = headers.get('x-powered-by', '').lower()
        if 'php' in powered_by:
            version_match = re.search(r'php/([\d.]+)', headers.get('x-powered-by', ''))
            version = f" {version_match.group(1)}" if version_match else ""
            return f'PHP{version}'
        elif 'asp.net' in powered_by:
            return 'ASP.NET'
        elif 'django' in powered_by:
            version_match = re.search(r'django/([\d.]+)', headers.get('x-powered-by', ''))
            version = f" {version_match.group(1)}" if version_match else ""
            return f'Django{version}'
        elif 'flask' in powered_by:
            return 'Flask'
        elif 'fastapi' in powered_by:
            return 'FastAPI'
        elif 'express' in powered_by:
            return 'Express.js'
        elif 'rails' in powered_by:
            return 'Ruby on Rails'
        elif 'laravel' in powered_by:
            return 'Laravel'
        elif 'symfony' in powered_by:
            return 'Symfony'
        elif 'spring' in powered_by:
            return 'Spring Boot'
        elif 'next.js' in powered_by:
            return 'Next.js'
        elif 'nuxt' in powered_by:
            return 'Nuxt.js'

        # CDN and Hosting Providers
        if 'x-amz-cf-id' in headers:
            return 'CloudFront (AWS)'
        elif 'cf-ray' in headers:
            return 'Cloudflare'
        elif 'x-vercel-id' in headers:
            return 'Vercel'
        elif 'x-netlify' in headers:
            return 'Netlify'
        elif 'x-github-request-id' in headers:
            return 'GitHub Pages'
        elif 'x-render-id' in headers:
            return 'Render'
        elif 'x-fly-request-id' in headers:
            return 'Fly.io'
        elif 'x-railway-static-url' in headers:
            return 'Railway'
        elif 'x-replit-user-name' in headers:
            return 'Replit'
        elif 'x-glitch-request-id' in headers:
            return 'Glitch'
        elif 'x-surge-id' in headers:
            return 'Surge.sh'

        # More CDN providers
        elif 'x-fastly-request-id' in headers:
            return 'Fastly'
        elif 'x-akamai-transformed' in headers:
            return 'Akamai'
        # More CDN providers
        elif 'x-fastly-request-id' in headers:
            return 'Fastly'
        elif 'x-akamai-transformed' in headers:
            return 'Akamai'
        elif 'x-varnish' in headers:
            return 'Varnish'
        elif 'x-squid-error' in headers:
            return 'Squid'
        elif 'x-keycdn-request-id' in headers:
            return 'KeyCDN'
        elif 'x-cdn' in headers and 'stackpath' in headers.get('x-cdn', '').lower():
            return 'StackPath'

        # Security and Performance
        elif 'x-xss-protection' in headers or 'x-content-type-options' in headers:
            # Check if it's a common security setup
            pass  # Continue to other checks

        # Government/Philippine-specific
        elif 'x-dost-gov-ph' in headers or 'gov.ph' in server.lower():
            return 'Philippine Government'
        elif 'x-bettergov' in headers:
            return 'BetterGov Platform'

        # Check response content for common signatures
        if response_text:
            # WordPress detection
            if 'wp-content' in response_text or 'wp-includes' in response_text or 'wp-json' in response_text:
                return 'WordPress'

            # Other CMS systems
            elif 'drupal' in response_text.lower():
                return 'Drupal'
            elif 'joomla' in response_text.lower():
                return 'Joomla'
            elif 'magento' in response_text.lower():
                return 'Magento'
            elif 'shopify' in response_text.lower():
                return 'Shopify'
            elif 'squarespace' in response_text.lower():
                return 'Squarespace'
            elif 'wix' in response_text.lower():
                return 'Wix'
            elif 'weebly' in response_text.lower():
                return 'Weebly'

            # Static site generators
            elif 'jekyll' in response_text.lower():
                return 'Jekyll'
            elif 'hugo' in response_text.lower():
                return 'Hugo'
            elif 'gatsby' in response_text.lower():
                return 'Gatsby'
            elif 'eleventy' in response_text.lower() or '11ty' in response_text.lower():
                return 'Eleventy'

            # Other frameworks
            elif 'react' in response_text.lower() and 'data-reactroot' in response_text.lower():
                return 'React'
            elif 'vue' in response_text.lower() and 'data-v-' in response_text:
                return 'Vue.js'
            elif 'angular' in response_text.lower():
                return 'Angular'

        return 'Unknown'

class UptimeChecker:
    def __init__(self):
        self.db_pool = None
        self.timeout = aiohttp.ClientTimeout(total=10, connect=5)

    async def get_db_pool(self):
        if self.db_pool is None:
            self.db_pool = await asyncpg.create_pool(
                os.getenv("DATABASE_URL", "postgresql://monitor:monitor123@db:5432/monitoring"),
                min_size=5,
                max_size=20
            )
        return self.db_pool

    async def get_active_subdomains(self):
        """Get all active subdomains from database"""
        pool = await self.get_db_pool()
        rows = await pool.fetch("""
            SELECT subdomain FROM monitoring.subdomains
            WHERE active = true
            ORDER BY subdomain
        """)
        return [row['subdomain'] for row in rows]

    async def get_active_subdomains_with_retry(self, max_retries=3):
        """Get active subdomains with retry logic for database connection issues"""
        for attempt in range(max_retries):
            try:
                return await self.get_active_subdomains()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                print(f"⚠️  Database connection attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(1)  # Wait 1 second before retry

    async def check_subdomain(self, session, subdomain):
        """Check a single subdomain and return results"""
        result = {
            'subdomain': subdomain,
            'up': False,
            'status_code': None,
            'response_time_ms': None,
            'platform': 'Unknown',
            'error_message': None,
            'headers': {}
        }

        start_time = time.time()

        try:
            # Try HTTPS first, then HTTP
            for protocol in ['https', 'http']:
                try:
                    url = f"{protocol}://{subdomain}"
                    async with session.get(url, allow_redirects=True) as response:
                        result['status_code'] = response.status
                        result['response_time_ms'] = (time.time() - start_time) * 1000

                        # Consider it "up" if status code is not a server error
                        result['up'] = response.status < 500

                        # Get headers for platform detection
                        headers_dict = dict(response.headers)
                        result['headers'] = headers_dict

                        # Try to get response text for additional detection (first 10KB)
                        try:
                            text = await response.text()
                            result['platform'] = PlatformDetector.detect_platform(
                                response.headers, text[:10240]
                            )
                        except:
                            result['platform'] = PlatformDetector.detect_platform(response.headers)

                        break  # Success with this protocol

                except aiohttp.ClientConnectorError as e:
                    result['error_message'] = f"Connection failed: {str(e)}"
                except asyncio.TimeoutError:
                    result['error_message'] = "Timeout"
                except Exception as e:
                    result['error_message'] = f"Error: {str(e)}"
                    continue

        except Exception as e:
            result['error_message'] = f"Unexpected error: {str(e)}"

        return result

    async def update_subdomain_platform(self, subdomain, platform):
        """Update the platform information for a subdomain"""
        pool = await self.get_db_pool()
        try:
            await pool.execute("""
                UPDATE monitoring.subdomains
                SET platform = $2, last_platform_check = $3
                WHERE subdomain = $1
            """, subdomain, platform, datetime.utcnow())
        except Exception as e:
            print(f"Error updating platform for {subdomain}: {e}")

    async def save_check_result(self, result):
        """Save the check result to database with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                pool = await self.get_db_pool()
                await pool.execute("""
                    INSERT INTO monitoring.uptime_checks
                    (time, subdomain, status_code, response_time_ms, up, platform, error_message, headers)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                datetime.utcnow(),
                result['subdomain'],
                result['status_code'],
                result['response_time_ms'],
                result['up'],
                result['platform'],
                result['error_message'],
                json.dumps(result.get('headers', {}))
                )
                return  # Success
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"❌ Failed to save result for {result['subdomain']} after {max_retries} attempts: {e}")
                else:
                    print(f"⚠️  Save attempt {attempt + 1} failed for {result['subdomain']}, retrying...")
                    await asyncio.sleep(0.5)

    async def run_checks(self):
        """Run uptime checks for all active subdomains"""
        print(f"[{datetime.now()}] Starting uptime checks...")

        try:
            # Get active subdomains with retry logic
            subdomains = await self.get_active_subdomains_with_retry()
            print(f"Checking {len(subdomains)} subdomains...")
        except Exception as e:
            print(f"❌ Failed to get subdomains: {e}")
            return

        if not subdomains:
            print("No active subdomains found. Run subdomain discovery first.")
            return

        # Create HTTP session with connection pooling
        connector = aiohttp.TCPConnector(
            limit=10,  # Max 10 concurrent connections
            ttl_dns_cache=300,  # DNS cache for 5 minutes
            use_dns_cache=True
        )

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={'User-Agent': 'BetterGov Monitoring/1.0'}
        ) as session:

            # Check all subdomains concurrently
            tasks = [self.check_subdomain(session, subdomain) for subdomain in subdomains]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successful_checks = 0
            for result in results:
                if isinstance(result, dict):
                    await self.save_check_result(result)
                    await self.update_subdomain_platform(result['subdomain'], result['platform'])

                    status = "✅ UP" if result['up'] else "❌ DOWN"
                    platform = result['platform'] or 'Unknown'
                    response_time = ".1f" if result['response_time_ms'] else "N/A"

                    print(f"  {status} {result['subdomain']} ({platform}) - {response_time}ms")
                    successful_checks += 1
                else:
                    print(f"  ❌ ERROR checking subdomain: {result}")

            print(f"Completed {successful_checks}/{len(subdomains)} checks")

    async def start_scheduler(self, interval_minutes=1):
        """Start the APScheduler for periodic checks"""
        print(f"Starting uptime monitoring scheduler (every {interval_minutes} minute(s))")

        scheduler = AsyncIOScheduler()

        # Add the uptime check job
        scheduler.add_job(
            self.run_checks,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id='uptime_check',
            name='Uptime Check',
            max_instances=1,
            replace_existing=True
        )

        # Add subdomain discovery job (run every 6 hours)
        scheduler.add_job(
            self.run_discovery,
            trigger=IntervalTrigger(hours=6),
            id='subdomain_discovery',
            name='Subdomain Discovery',
            max_instances=1,
            replace_existing=True
        )

        # Start the scheduler
        scheduler.start()

        print("Scheduler started. Press Ctrl+C to exit.")

        # Keep the event loop running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            print("Shutting down scheduler...")
            scheduler.shutdown()
            print("Scheduler stopped.")

    async def run_discovery(self):
        """Run subdomain discovery"""
        try:
            from subdomain_discovery import SubdomainDiscovery
            discovery = SubdomainDiscovery()
            subdomains = await discovery.discover_all()
            print(f"Discovery complete: found {len(subdomains)} subdomains")
        except Exception as e:
            print(f"Error during subdomain discovery: {e}")

    async def run_continuous(self, interval_minutes=1):
        """Legacy method for backward compatibility"""
        await self.start_scheduler(interval_minutes)

async def main():
    """Main function for single run or continuous monitoring"""
    import sys

    checker = UptimeChecker()

    if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
        # Continuous mode
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        await checker.run_continuous(interval)
    else:
        # Single run mode
        await checker.run_checks()
        print("Uptime check complete!")

if __name__ == "__main__":
    asyncio.run(main())
