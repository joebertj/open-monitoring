#!/usr/bin/env python3
"""
Scrape BetterGovPH website to find actual projects from "Our Projects" section
"""

import requests
from bs4 import BeautifulSoup
import re
import asyncio
import asyncpg
import os
from urllib.parse import urljoin, urlparse
from requests_html import AsyncHTMLSession

async def scrape_bettergov_projects():
    """Scrape the BetterGovPH website to find actual project subdomains"""

    base_url = "https://bettergov.ph"
    projects = set()

    try:
        print("🔍 Scraping BetterGovPH website for projects (with JavaScript rendering)...")

        # Use requests-html to render JavaScript
        session = AsyncHTMLSession()
        response = await session.get(base_url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        # Wait for JavaScript to load
        await response.html.arender(timeout=20, sleep=3)

        # Now parse the rendered HTML
        soup = BeautifulSoup(response.html.html, 'html.parser')

        # Look for all links that contain bettergov.ph in the rendered content
        all_links = soup.find_all('a', href=True)

        for link in all_links:
            href = link.get('href')
            if href and 'bettergov.ph' in href:
                # Convert relative URLs to absolute
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)

                # Check if it's a subdomain
                if parsed.netloc and parsed.netloc != 'bettergov.ph':
                    subdomain = parsed.netloc
                    # Only add if it's actually a subdomain of bettergov.ph
                    if subdomain.endswith('.bettergov.ph'):
                        projects.add(subdomain)
                        print(f"🔗 Found project link: {subdomain}")

        # Look for project/portfolio/initiative sections in rendered content
        project_selectors = [
            '[class*="project"]', '[class*="portfolio"]', '[class*="work"]',
            '[class*="initiative"]', '[id*="project"]', '[id*="portfolio"]'
        ]

        for selector in project_selectors:
            project_sections = soup.select(selector)
            for section in project_sections:
                links = section.find_all('a', href=True)
                for link in links:
                    href = link.get('href')
                    if href and 'bettergov.ph' in href:
                        full_url = urljoin(base_url, href)
                        parsed = urlparse(full_url)
                        if parsed.netloc and parsed.netloc.endswith('.bettergov.ph'):
                            projects.add(parsed.netloc)
                            print(f"📁 Found in project section: {parsed.netloc}")

        # Look for text content that mentions subdomains in rendered HTML
        text_content = soup.get_text()
        subdomain_mentions = re.findall(r'(\w+\.bettergov\.ph)', text_content)
        for mention in subdomain_mentions:
            if mention not in ['www.bettergov.ph', 'api.bettergov.ph', 'mail.bettergov.ph']:
                projects.add(mention)
                print(f"📝 Found subdomain mention: {mention}")

            # Confirm all found projects actually exist and are reachable
            confirmed_projects = set()
            for project in projects.copy():
                try:
                    test_response = requests.head(f"https://{project}", timeout=5)
                    if test_response.status_code == 200:
                        confirmed_projects.add(project)
                        print(f"✅ Confirmed {project} exists")
                    else:
                        print(f"⚠️ {project} returned status {test_response.status_code}")
                except Exception as e:
                    print(f"⚠️ {project} is not reachable: {e}")

            projects = confirmed_projects

        # Remove common non-project subdomains
        exclude = {'www.bettergov.ph', 'api.bettergov.ph', 'mail.bettergov.ph', 'ftp.bettergov.ph', 'smtp.bettergov.ph'}
        projects = projects - exclude

        print(f"\n🎯 Found {len(projects)} project subdomains:")
        for project in sorted(projects):
            print(f"  • {project}")

        return list(projects) if projects else ['visualizations.bettergov.ph']

    except Exception as e:
        print(f"❌ Error scraping website: {e}")
        # Return known projects
        return ['visualizations.bettergov.ph', 'budget.bettergov.ph']

async def update_projects_in_db(projects):
    """Update the database with the scraped projects"""

    print("\n💾 Updating database with discovered projects...")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable must be set")
    pool = await asyncpg.create_pool(database_url)

    try:
        # Move current projects to other_dns (except visualizations)
        await pool.execute("""
            INSERT INTO monitoring.other_dns (subdomain, discovered_at, last_seen, active, platform)
            SELECT subdomain, discovered_at, last_seen, active, platform
            FROM monitoring.subdomains
            WHERE subdomain NOT IN ('bettergov.ph', 'visualizations.bettergov.ph')
            ON CONFLICT (subdomain) DO NOTHING
        """)

        # Remove old projects
        await pool.execute("""
            DELETE FROM monitoring.subdomains
            WHERE subdomain NOT IN ('bettergov.ph', 'visualizations.bettergov.ph')
        """)

        # Add discovered projects
        for project in projects:
            await pool.execute("""
                INSERT INTO monitoring.subdomains (domain, subdomain, discovered_at, active)
                VALUES ('bettergov.ph', $1, NOW(), true)
                ON CONFLICT (subdomain) DO NOTHING
            """, project)

        print(f"✅ Database updated with {len(projects)} projects")

    finally:
        await pool.close()

async def main():
    """Main function"""
    print("🚀 BetterGovPH Project Discovery")
    print("=" * 40)

    # Scrape projects from website
    projects = await scrape_bettergov_projects()

    if projects:
        # Update database
        await update_projects_in_db(projects)
        print("\n🎉 Project discovery completed!")
    else:
        print("❌ No projects found")

if __name__ == "__main__":
    asyncio.run(main())
