#!/usr/bin/env python3
"""
Subdomain discovery for bettergov.ph
Discovers subdomains through various methods and stores them in the database
"""

import asyncio
import aiohttp
import asyncpg
import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os

# Known subdomains (including unlisted ones)
# Note: www.bettergov.ph is excluded as it just redirects to bettergov.ph
KNOWN_SUBDOMAINS = [
    'bettergov.ph',  # Root domain
    'visualizations.bettergov.ph',
    'api.bettergov.ph',
    'admin.bettergov.ph',
    'portal.bettergov.ph',
    'dashboard.bettergov.ph',
    'docs.bettergov.ph',
    'dev.bettergov.ph',
    'staging.bettergov.ph',
    'test.bettergov.ph',
    'monitoring.bettergov.ph'
]

# Common subdomain prefixes to try
COMMON_PREFIXES = [
    'www', 'api', 'admin', 'portal', 'dashboard', 'docs', 'dev', 'staging',
    'test', 'app', 'web', 'service', 'services', 'data', 'db', 'database',
    'auth', 'login', 'secure', 'ssl', 'mail', 'email', 'smtp', 'ftp',
    'git', 'gitlab', 'github', 'jenkins', 'ci', 'cd', 'build', 'deploy',
    'monitor', 'monitoring', 'metrics', 'logs', 'log', 'status', 'health',
    'ping', 'check', 'probe', 'grafana', 'kibana', 'elasticsearch'
]

class SubdomainDiscovery:
    def __init__(self):
        self.base_domain = 'bettergov.ph'
        self.found_subdomains = set()
        self.db_pool = None

    async def get_db_pool(self):
        if self.db_pool is None:
            self.db_pool = await asyncpg.create_pool(
                os.getenv("DATABASE_URL", "postgresql://monitor:monitor123@db:5432/monitoring"),
                min_size=5,
                max_size=20
            )
        return self.db_pool

    async def discover_from_website(self):
        """Parse the main bettergov.ph website for subdomain links"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://{self.base_domain}', timeout=10) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Find all links
                        for link in soup.find_all('a', href=True):
                            href = link['href']
                            parsed = urlparse(href)

                            # Check for subdomains
                            if parsed.netloc and parsed.netloc.endswith(f'.{self.base_domain}'):
                                self.found_subdomains.add(parsed.netloc.lower())

                            # Also check relative URLs that might point to subdomains
                            elif href.startswith('//') and href.endswith(f'.{self.base_domain}'):
                                subdomain = href[2:].lower()
                                self.found_subdomains.add(subdomain)

        except Exception as e:
            print(f"Error discovering from website: {e}")

    async def check_common_subdomains(self):
        """Try common subdomain prefixes"""
        connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []

            # Check known subdomains (including root domain)
            for subdomain in KNOWN_SUBDOMAINS:
                tasks.append(self.check_subdomain(session, subdomain))

            # Check common prefixes (but skip www since we handle it specially)
            for prefix in COMMON_PREFIXES:
                if prefix == 'www':  # Skip www, we handle it below
                    continue
                subdomain = f"{prefix}.{self.base_domain}"
                tasks.append(self.check_subdomain(session, subdomain))

            # Special handling for www subdomain - exclude even if it resolves
            # Since www.bettergov.ph just redirects to bettergov.ph, we don't need to monitor it
            # The frontend can handle the redirect

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, str):
                    self.found_subdomains.add(result.lower())

    async def check_subdomain(self, session, subdomain):
        """Check if a subdomain exists by making a HEAD request"""
        try:
            # Try HTTPS first, then HTTP
            for protocol in ['https', 'http']:
                try:
                    url = f"{protocol}://{subdomain}"
                    async with session.head(url) as response:
                        if response.status < 400:  # Consider redirects and client errors as valid
                            return subdomain
                except:
                    continue
        except:
            pass
        return None

    async def save_subdomains_to_db(self):
        """Save discovered subdomains to database"""
        pool = await self.get_db_pool()

        for subdomain in self.found_subdomains:
            try:
                await pool.execute("""
                    INSERT INTO monitoring.subdomains (domain, subdomain, discovered_at, active)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (subdomain) DO UPDATE SET
                        last_seen = $3,
                        active = $4
                """, self.base_domain, subdomain, datetime.utcnow(), True)
            except Exception as e:
                print(f"Error saving subdomain {subdomain}: {e}")

    async def discover_all(self):
        """Run all discovery methods"""
        print("Starting subdomain discovery for bettergov.ph...")

        # Add known subdomains first
        for subdomain in KNOWN_SUBDOMAINS:
            self.found_subdomains.add(subdomain.lower())

        # Discover from website
        print("Parsing main website for links...")
        await self.discover_from_website()

        # Check common subdomains
        print("Checking common subdomain prefixes...")
        await self.check_common_subdomains()

        # Save to database
        print(f"Found {len(self.found_subdomains)} subdomains, saving to database...")
        await self.save_subdomains_to_db()

        print("Subdomain discovery complete!")
        return list(self.found_subdomains)

async def main():
    """Main function to run subdomain discovery"""
    discovery = SubdomainDiscovery()
    subdomains = await discovery.discover_all()

    print(f"\nDiscovered subdomains:")
    for subdomain in sorted(subdomains):
        print(f"  - {subdomain}")

if __name__ == "__main__":
    asyncio.run(main())
